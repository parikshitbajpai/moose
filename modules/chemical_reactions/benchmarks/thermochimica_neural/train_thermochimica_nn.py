#!/usr/bin/env python3
"""Train and export a multi-output Thermochimica TorchScript surrogate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn


def _temperature_kelvin(values: np.ndarray, unit: str) -> np.ndarray:
    if unit == "K":
        return values
    if unit == "C":
        return values + 273.15
    if unit == "F":
        return (values - 32.0) * 5.0 / 9.0 + 273.15
    if unit == "R":
        return values * 5.0 / 9.0
    raise ValueError(f"Unsupported temperature unit: {unit}")


def _pressure_bar(values: np.ndarray, unit: str) -> np.ndarray:
    factors = {"bar": 1.0, "atm": 1.01325, "psi": 0.0689475729318, "Pa": 1e-5, "kPa": 1e-2}
    try:
        return values * factors[unit]
    except KeyError as error:
        raise ValueError(f"Unsupported pressure unit: {unit}") from error


def _read_csv(path: Path) -> dict[str, np.ndarray]:
    table = np.genfromtxt(path, delimiter=",", names=True)
    if table.shape == ():
        table = table.reshape(1)
    return {name: np.asarray(table[name], dtype=np.float64) for name in table.dtype.names or ()}


def _columns(table: dict[str, np.ndarray], names: list[str]) -> np.ndarray:
    missing = [name for name in names if name not in table]
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(missing)}")
    return np.column_stack([table[name] for name in names])


def _canonical_data(table: dict[str, np.ndarray], spec: dict) -> tuple[np.ndarray, np.ndarray]:
    rows = len(next(iter(table.values())))
    temperature_values = (
        table[spec["temperature_column"]]
        if "temperature_column" in spec
        else np.full(rows, float(spec["temperature"]))
    )
    pressure_values = (
        table[spec["pressure_column"]]
        if "pressure_column" in spec
        else np.full(rows, float(spec["pressure"]))
    )
    temperature = _temperature_kelvin(temperature_values, spec["temperature_unit"])
    pressure = _pressure_bar(pressure_values, spec["pressure_unit"])
    composition = _columns(table, spec["elements"])
    total = composition.sum(axis=1)
    if np.any(~np.isfinite(composition)) or np.any(composition < 0.0):
        raise ValueError("Element compositions must be finite and nonnegative")
    if np.any(total <= 0.0) or np.any(temperature <= 0.0) or np.any(pressure <= 0.0):
        raise ValueError("Temperature, pressure, and total composition must be positive")

    inputs = np.column_stack(
        [np.log(temperature / 298.15), np.log(pressure), composition / total[:, None]]
    )
    outputs = _columns(table, [output["variable"] for output in spec["outputs"]])
    for column, output in enumerate(spec["outputs"]):
        if output.get("extensive", False):
            outputs[:, column] /= total
    if np.any(~np.isfinite(outputs)):
        raise ValueError("Training outputs must be finite")
    return inputs, outputs


class ThermochimicaNetwork(nn.Module):
    def __init__(
        self,
        input_mean: torch.Tensor,
        input_scale: torch.Tensor,
        output_mean: torch.Tensor,
        output_scale: torch.Tensor,
    ):
        super().__init__()
        self.register_buffer("input_mean", input_mean)
        self.register_buffer("input_scale", input_scale)
        self.register_buffer("output_mean", output_mean)
        self.register_buffer("output_scale", output_scale)
        width = input_mean.numel()
        outputs = output_mean.numel()
        self.layers = nn.Sequential(
            nn.Linear(width, 128),
            nn.SiLU(),
            nn.Linear(128, 128),
            nn.SiLU(),
            nn.Linear(128, 64),
            nn.SiLU(),
            nn.Linear(64, outputs),
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        normalized = (values - self.input_mean) / self.input_scale
        return self.layers(normalized) * self.output_scale + self.output_mean


def _metrics(expected: np.ndarray, predicted: np.ndarray, outputs: list[dict]) -> list[dict]:
    metrics = []
    for column, output in enumerate(outputs):
        difference = np.abs(expected[:, column] - predicted[:, column])
        scale = np.maximum(np.abs(expected[:, column]), np.abs(predicted[:, column]))
        relative = difference / np.maximum(scale, np.finfo(np.float64).tiny)
        absolute_tolerance = float(output.get("absolute_tolerance", 0.0))
        relative_tolerance = float(output.get("relative_tolerance", 1e-3))
        accepted = difference <= absolute_tolerance + relative_tolerance * scale
        metrics.append(
            {
                "variable": output["variable"],
                "max_absolute_error": float(difference.max()),
                "max_relative_error": float(relative.max()),
                "accepted_fraction": float(accepted.mean()),
            }
        )
    return metrics


def train(data_path: Path, spec_path: Path, output_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    inputs, responses = _canonical_data(_read_csv(data_path), spec)
    seed = int(spec.get("seed", 11))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(inputs))
    validation_size = max(1, int(round(len(inputs) * float(spec.get("validation_fraction", 0.2)))))
    validation_rows = order[:validation_size]
    training_rows = order[validation_size:]
    if not len(training_rows):
        raise ValueError("At least two training rows are required")

    torch.manual_seed(seed)
    x_train = torch.tensor(inputs[training_rows], dtype=torch.float32)
    y_train = torch.tensor(responses[training_rows], dtype=torch.float32)
    x_validation = torch.tensor(inputs[validation_rows], dtype=torch.float32)
    y_validation = torch.tensor(responses[validation_rows], dtype=torch.float32)

    input_mean = x_train.mean(dim=0)
    input_scale = x_train.std(dim=0).clamp_min(1e-12)
    output_mean = y_train.mean(dim=0)
    output_scale = y_train.std(dim=0).clamp_min(1e-12)
    model = ThermochimicaNetwork(input_mean, input_scale, output_mean, output_scale)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(spec.get("learning_rate", 1e-3)))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, factor=0.5, patience=max(10, int(spec.get("patience", 100)) // 4), min_lr=1e-6
    )
    loss_function = nn.MSELoss()

    best_loss = float("inf")
    best_state = None
    remaining_patience = int(spec.get("patience", 100))
    for epoch in range(int(spec.get("epochs", 2000))):
        model.train()
        optimizer.zero_grad()
        loss = loss_function(
            (model(x_train) - output_mean) / output_scale,
            (y_train - output_mean) / output_scale,
        )
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = loss_function(
                (model(x_validation) - output_mean) / output_scale,
                (y_validation - output_mean) / output_scale,
            ).item()
        scheduler.step(validation_loss)
        if validation_loss < best_loss - 1e-10:
            best_loss = validation_loss
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
            remaining_patience = int(spec.get("patience", 100))
        else:
            remaining_patience -= 1
            if remaining_patience == 0:
                break

    if best_state is None:
        raise RuntimeError("Training did not produce a finite validation loss")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        predicted = model(x_validation).cpu().numpy().astype(np.float64)

    database_path = (spec_path.parent / spec["database"]).resolve()
    metadata = {
        "schema_version": 1,
        "archive_type": "thermochimica_neural_torchscript",
        "database_sha256": hashlib.sha256(database_path.read_bytes()).hexdigest(),
        "elements": spec["elements"],
        "temperature_unit": spec["temperature_unit"],
        "pressure_unit": spec["pressure_unit"],
        "composition_unit": spec["composition_unit"],
        "phase_selection": spec.get("phase_selection", {"mode": "none", "phases": []}),
        "outputs": spec["outputs"],
        "input_lower_bounds": inputs.min(axis=0).tolist(),
        "input_upper_bounds": inputs.max(axis=0).tolist(),
        "torch_version": torch.__version__,
        "validation_loss": best_loss,
        "validation_metrics": _metrics(responses[validation_rows], predicted, spec["outputs"]),
    }
    example = torch.zeros((2, inputs.shape[1]), dtype=torch.float32)
    archive = torch.jit.trace(model, example)
    torch.jit.save(archive, output_path, _extra_files={"metadata.json": json.dumps(metadata)})
    report_path = output_path.with_suffix(".validation.json")
    report_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="Exact Thermochimica CSV data")
    parser.add_argument("--spec", type=Path, required=True, help="Training and archive JSON specification")
    parser.add_argument("--output", type=Path, required=True, help="Output TorchScript archive")
    arguments = parser.parse_args()
    metadata = train(arguments.data, arguments.spec, arguments.output)
    print(json.dumps({"archive": str(arguments.output), "validation": metadata["validation_metrics"]}))


if __name__ == "__main__":
    main()
