#!/usr/bin/env python3
"""Train and export a guarded multi-output Thermochimica TorchScript surrogate."""

from __future__ import annotations

import argparse
import copy
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


def _prepare_outputs(outputs: list[dict]) -> tuple[list[dict], np.ndarray, np.ndarray]:
    prepared = copy.deepcopy(outputs)
    kinds = []
    scales = []
    for output in prepared:
        transform = output.setdefault("transform", {"kind": "linear"})
        kind = transform.get("kind", "linear")
        if kind not in ("linear", "log1p"):
            raise ValueError(
                f"Output '{output['variable']}' has unsupported transform kind '{kind}'"
            )
        scale = float(transform.get("scale", 1.0))
        if kind == "log1p" and (not output.get("nonnegative", False) or scale <= 0.0):
            raise ValueError(
                f"Output '{output['variable']}' requires a positive log1p scale and "
                "nonnegative=true"
            )
        transform["kind"] = kind
        if kind == "log1p":
            transform["scale"] = scale
        kinds.append(1 if kind == "log1p" else 0)
        scales.append(scale)
    return prepared, np.asarray(kinds, dtype=np.int64), np.asarray(scales, dtype=np.float64)


def _transform_outputs(values: np.ndarray, kinds: np.ndarray, scales: np.ndarray) -> np.ndarray:
    transformed = values.copy()
    for column in range(values.shape[1]):
        if kinds[column] == 1:
            if np.any(values[:, column] < 0.0):
                raise ValueError("A log1p output transform received a negative training value")
            transformed[:, column] = np.log1p(values[:, column] / scales[column])
    return transformed


def _phase_configuration(
    spec: dict, outputs: list[dict], responses: np.ndarray
) -> tuple[dict, np.ndarray]:
    gate = copy.deepcopy(spec.get("phase_gate", {}))
    phases = gate.get("phases", [])
    labels = np.zeros((responses.shape[0], len(phases)), dtype=np.float64)
    variables = [output["variable"] for output in outputs]
    prepared_phases = []
    for column, phase in enumerate(phases):
        variable = phase["amount_variable"]
        if variable not in variables:
            raise ValueError(f"Phase gate references unknown amount output '{variable}'")
        output_index = variables.index(variable)
        if not outputs[output_index].get("nonnegative", False):
            raise ValueError(f"Phase gate amount output '{variable}' must be nonnegative")
        threshold = float(phase.get("presence_threshold", 1e-10))
        if threshold < 0.0:
            raise ValueError("Phase presence thresholds must be nonnegative")
        labels[:, column] = responses[:, output_index] > threshold
        prepared = copy.deepcopy(phase)
        prepared["output_index"] = output_index
        prepared["presence_threshold"] = threshold
        prepared_phases.append(prepared)
    confidence = float(gate.get("confidence_threshold", 0.99))
    if not 0.5 <= confidence <= 1.0:
        raise ValueError("Phase confidence threshold must be between 0.5 and 1")
    return {"confidence_threshold": confidence, "phases": prepared_phases}, labels


def _invariant_groups(spec: dict, outputs: list[dict]) -> list[dict]:
    variables = [output["variable"] for output in outputs]
    groups = copy.deepcopy(spec.get("invariant_groups", []))
    for group in groups:
        unknown = [variable for variable in group["variables"] if variable not in variables]
        if unknown:
            raise ValueError(
                f"Invariant group '{group.get('name', '')}' references unknown outputs: "
                + ", ".join(unknown)
            )
        group["output_indices"] = [variables.index(variable) for variable in group["variables"]]
        group["target"] = float(group.get("target", 1.0))
        group["tolerance"] = float(group.get("tolerance", 1e-3))
        if group["tolerance"] < 0.0:
            raise ValueError("Invariant group tolerances must be nonnegative")
        if any(not outputs[index].get("fraction", False) for index in group["output_indices"]):
            raise ValueError("Coupled invariant groups must reference fraction outputs")
    return groups


def _nearest_distances(
    queries: np.ndarray,
    anchors: np.ndarray,
    query_labels: np.ndarray | None = None,
    anchor_labels: np.ndarray | None = None,
) -> np.ndarray:
    distances = np.empty(len(queries), dtype=np.float64)
    for row, query in enumerate(queries):
        candidates = anchors
        if query_labels is not None and anchor_labels is not None and query_labels.shape[1]:
            mask = np.all(anchor_labels == query_labels[row], axis=1)
            if np.any(mask):
                candidates = anchors[mask]
        differences = candidates - query
        distances[row] = np.sqrt(np.min(np.sum(differences * differences, axis=1)))
    return distances


class ThermochimicaNetwork(nn.Module):
    def __init__(
        self,
        input_mean: torch.Tensor,
        input_scale: torch.Tensor,
        output_mean: torch.Tensor,
        output_scale: torch.Tensor,
        output_transform_kind: torch.Tensor,
        output_transform_scale: torch.Tensor,
        support_points: torch.Tensor,
        support_labels: torch.Tensor,
        support_signatures: torch.Tensor,
        phase_count: int,
    ):
        super().__init__()
        self.register_buffer("input_mean", input_mean)
        self.register_buffer("input_scale", input_scale)
        self.register_buffer("output_mean", output_mean)
        self.register_buffer("output_scale", output_scale)
        self.register_buffer("output_transform_kind", output_transform_kind)
        self.register_buffer("output_transform_scale", output_transform_scale)
        self.register_buffer("support_points", support_points)
        signature_matches = torch.all(
            support_signatures.unsqueeze(1) == support_labels.unsqueeze(0), dim=2
        )
        self.register_buffer(
            "support_penalty",
            (~signature_matches).to(torch.float32) * torch.tensor(1e30, dtype=torch.float32),
        )
        self.register_buffer("phase_temperature", torch.ones(1, dtype=torch.float32))
        self.phase_count = phase_count
        width = input_mean.numel()
        self.layers = nn.Sequential(
            nn.Linear(width, 128),
            nn.SiLU(),
            nn.Linear(128, 128),
            nn.SiLU(),
            nn.Linear(128, 64),
            nn.SiLU(),
        )
        self.regression = nn.Linear(64, output_mean.numel())
        self.phase_classifier = nn.Linear(64, max(phase_count, 1))

    def features(self, values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        normalized = (values - self.input_mean) / self.input_scale
        return normalized, self.layers(normalized)

    def encoded_outputs(self, values: torch.Tensor) -> torch.Tensor:
        _, features = self.features(values)
        return self.regression(features) * self.output_scale + self.output_mean

    def phase_logits(self, values: torch.Tensor) -> torch.Tensor:
        _, features = self.features(values)
        return self.phase_classifier(features)[:, : self.phase_count]

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        normalized, features = self.features(values)
        encoded = self.regression(features) * self.output_scale + self.output_mean
        physical = torch.where(
            self.output_transform_kind == 1,
            self.output_transform_scale * torch.expm1(encoded),
            encoded,
        )
        differences = normalized.unsqueeze(1) - self.support_points.unsqueeze(0)
        squared_distance = torch.sum(differences * differences, dim=2)
        support_distance = torch.sqrt(
            (squared_distance.unsqueeze(1) + self.support_penalty.unsqueeze(0))
            .min(dim=2)
            .values
        )
        if self.phase_count:
            logits = self.phase_classifier(features)[:, : self.phase_count] / self.phase_temperature
            return torch.cat((physical, logits, support_distance), dim=1)
        return torch.cat((physical, support_distance), dim=1)


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


def _calibrate_phase_temperature(
    model: ThermochimicaNetwork, values: torch.Tensor, labels: torch.Tensor
) -> float:
    if labels.shape[1] == 0:
        return 1.0
    with torch.no_grad():
        logits = model.phase_logits(values)
        loss_function = nn.BCEWithLogitsLoss()
        candidates = torch.logspace(-1.0, 1.0, 81)
        losses = torch.stack([loss_function(logits / value, labels) for value in candidates])
        temperature = float(candidates[int(torch.argmin(losses))])
        model.phase_temperature.fill_(temperature)
        return temperature


def train(
    data_path: Path,
    spec_path: Path,
    output_path: Path,
    validation_path: Path | None = None,
) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    outputs, transform_kinds, transform_scales = _prepare_outputs(spec["outputs"])
    inputs, responses = _canonical_data(_read_csv(data_path), spec)
    phase_gate, labels = _phase_configuration(spec, outputs, responses)
    seed = int(spec.get("seed", 11))

    if validation_path is None:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(inputs))
        validation_size = max(
            1, int(round(len(inputs) * float(spec.get("validation_fraction", 0.2))))
        )
        validation_rows = order[:validation_size]
        training_rows = order[validation_size:]
        if not len(training_rows):
            raise ValueError("At least two training rows are required")
        training_inputs = inputs[training_rows]
        training_responses = responses[training_rows]
        training_labels = labels[training_rows]
        validation_inputs = inputs[validation_rows]
        validation_responses = responses[validation_rows]
        validation_labels = labels[validation_rows]
        split = {
            "kind": "seeded_random",
            "seed": seed,
            "training_rows": len(training_rows),
            "validation_rows": len(validation_rows),
        }
    else:
        validation_inputs, validation_responses = _canonical_data(
            _read_csv(validation_path), spec
        )
        _, validation_labels = _phase_configuration(spec, outputs, validation_responses)
        training_inputs = inputs
        training_responses = responses
        training_labels = labels
        split = {
            "kind": "explicit",
            "training_rows": len(training_inputs),
            "validation_rows": len(validation_inputs),
            "validation_file": str(validation_path),
        }
    if len(training_inputs) < 2 or not len(validation_inputs):
        raise ValueError("Training requires at least two rows and validation requires one row")

    transformed_training = _transform_outputs(
        training_responses, transform_kinds, transform_scales
    )
    transformed_validation = _transform_outputs(
        validation_responses, transform_kinds, transform_scales
    )
    torch.manual_seed(seed)
    x_train = torch.tensor(training_inputs, dtype=torch.float32)
    y_train = torch.tensor(transformed_training, dtype=torch.float32)
    phase_train = torch.tensor(training_labels, dtype=torch.float32)
    x_validation = torch.tensor(validation_inputs, dtype=torch.float32)
    y_validation = torch.tensor(transformed_validation, dtype=torch.float32)
    phase_validation = torch.tensor(validation_labels, dtype=torch.float32)

    input_mean = x_train.mean(dim=0)
    input_scale = x_train.std(dim=0).clamp_min(1e-12)
    output_mean = y_train.mean(dim=0)
    output_scale = y_train.std(dim=0).clamp_min(1e-12)
    normalized_support = (x_train - input_mean) / input_scale
    training_label_rows = np.asarray(training_labels, dtype=np.int64)
    validation_label_rows = np.asarray(validation_labels, dtype=np.int64)
    validation_signatures = np.unique(validation_label_rows, axis=0)
    calibrated_signatures = np.asarray(
        [
            signature
            for signature in validation_signatures
            if np.any(np.all(training_label_rows == signature, axis=1))
        ],
        dtype=np.int64,
    )
    if not len(calibrated_signatures):
        raise ValueError("No validation phase assemblage is represented in the training data")
    maximum_anchors = int(spec.get("support", {}).get("max_anchors", 4096))
    if maximum_anchors < len(calibrated_signatures):
        raise ValueError("Support max_anchors must retain at least one anchor per assemblage")
    anchors_per_assemblage = maximum_anchors // len(calibrated_signatures)
    selected_anchor_rows = []
    for signature in calibrated_signatures:
        candidates = np.flatnonzero(np.all(training_label_rows == signature, axis=1))
        count = min(len(candidates), anchors_per_assemblage)
        selected_anchor_rows.extend(
            candidates[
                np.linspace(0, len(candidates) - 1, count, dtype=np.int64)
            ].tolist()
        )
    selected_anchor_rows = np.asarray(sorted(selected_anchor_rows), dtype=np.int64)
    embedded_support_points = normalized_support[selected_anchor_rows]
    support_labels = training_label_rows[selected_anchor_rows]
    model = ThermochimicaNetwork(
        input_mean,
        input_scale,
        output_mean,
        output_scale,
        torch.tensor(transform_kinds, dtype=torch.int64),
        torch.tensor(transform_scales, dtype=torch.float32),
        embedded_support_points,
        torch.tensor(support_labels, dtype=torch.int64),
        torch.tensor(calibrated_signatures, dtype=torch.int64),
        phase_train.shape[1],
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=float(spec.get("learning_rate", 1e-3)))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, factor=0.5, patience=max(10, int(spec.get("patience", 100)) // 4), min_lr=1e-6
    )
    regression_loss = nn.MSELoss()
    classification_loss = nn.BCEWithLogitsLoss()
    phase_loss_weight = float(spec.get("phase_gate", {}).get("loss_weight", 0.1))

    best_loss = float("inf")
    best_state = None
    remaining_patience = int(spec.get("patience", 100))
    for _ in range(int(spec.get("epochs", 2000))):
        model.train()
        optimizer.zero_grad()
        loss = regression_loss(
            (model.encoded_outputs(x_train) - output_mean) / output_scale,
            (y_train - output_mean) / output_scale,
        )
        if phase_train.shape[1]:
            loss = loss + phase_loss_weight * classification_loss(
                model.phase_logits(x_train), phase_train
            )
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = regression_loss(
                (model.encoded_outputs(x_validation) - output_mean) / output_scale,
                (y_validation - output_mean) / output_scale,
            )
            if phase_validation.shape[1]:
                validation_loss = validation_loss + phase_loss_weight * classification_loss(
                    model.phase_logits(x_validation), phase_validation
                )
            validation_loss_value = float(validation_loss)
        scheduler.step(validation_loss_value)
        if validation_loss_value < best_loss - 1e-10:
            best_loss = validation_loss_value
            best_state = {
                name: value.detach().clone() for name, value in model.state_dict().items()
            }
            remaining_patience = int(spec.get("patience", 100))
        else:
            remaining_patience -= 1
            if remaining_patience == 0:
                break

    if best_state is None:
        raise RuntimeError("Training did not produce a finite validation loss")
    model.load_state_dict(best_state)
    model.eval()
    phase_temperature = _calibrate_phase_temperature(
        model, x_validation, phase_validation
    )
    with torch.no_grad():
        predicted = (
            model(x_validation)[:, : len(outputs)].cpu().numpy().astype(np.float64)
        )

    normalized_training = (
        training_inputs - input_mean.numpy().astype(np.float64)
    ) / input_scale.numpy().astype(np.float64)
    normalized_validation = (
        validation_inputs - input_mean.numpy().astype(np.float64)
    ) / input_scale.numpy().astype(np.float64)
    normalized_anchor_points = normalized_training[selected_anchor_rows]
    support_quantile = float(spec.get("support", {}).get("quantile", 0.99))
    support_padding = float(spec.get("support", {}).get("padding", 1.25))
    if not 0.0 < support_quantile <= 1.0 or support_padding <= 0.0:
        raise ValueError("Support quantile and padding must be positive")
    support_offset = len(outputs) + len(phase_gate["phases"])
    support_assemblages = []
    for column, signature in enumerate(calibrated_signatures):
        training_mask = np.all(training_label_rows == signature, axis=1)
        anchor_mask = np.all(support_labels == signature, axis=1)
        validation_mask = np.all(validation_label_rows == signature, axis=1)
        support_distances = _nearest_distances(
            normalized_validation[validation_mask],
            normalized_anchor_points[anchor_mask],
        )
        support_assemblages.append(
            {
                "signature": signature.tolist(),
                "training_rows": int(training_mask.sum()),
                "anchor_count": int(anchor_mask.sum()),
                "validation_count": int(validation_mask.sum()),
                "distance_index": support_offset + column,
                "radius": max(
                    1e-6,
                    support_padding
                    * float(np.quantile(support_distances, support_quantile)),
                ),
            }
        )

    database_path = (spec_path.parent / spec["database"]).resolve()
    phase_gate["temperature"] = phase_temperature
    metadata = {
        "schema_version": 2,
        "archive_type": "thermochimica_neural_torchscript",
        "database_sha256": hashlib.sha256(database_path.read_bytes()).hexdigest(),
        "elements": spec["elements"],
        "temperature_unit": spec["temperature_unit"],
        "pressure_unit": spec["pressure_unit"],
        "composition_unit": spec["composition_unit"],
        "thermodynamic_units": {
            "system_gibbs_energy": "J",
            "chemical_and_element_potentials": "J/mol",
            "fractions": "1",
            "vapor_pressure": spec["pressure_unit"],
            "extensive_training_basis": "per_unit_total_input",
        },
        "phase_selection": spec.get("phase_selection", {"mode": "none", "phases": []}),
        "outputs": outputs,
        "input_lower_bounds": training_inputs.min(axis=0).tolist(),
        "input_upper_bounds": training_inputs.max(axis=0).tolist(),
        "phase_gate": phase_gate,
        "support": {
            "coordinate_system": "training_standardized_euclidean",
            "training_rows": len(training_inputs),
            "anchor_count": len(selected_anchor_rows),
            "max_anchors": maximum_anchors,
            "quantile": support_quantile,
            "padding": support_padding,
            "assemblages": support_assemblages,
        },
        "invariant_groups": _invariant_groups(spec, outputs),
        "model_output_layout": {
            "regression_width": len(outputs),
            "phase_logit_offset": len(outputs),
            "phase_logit_count": len(phase_gate["phases"]),
            "support_distance_offset": support_offset,
            "support_distance_count": len(support_assemblages),
        },
        "split": split,
        "torch_version": torch.__version__,
        "validation_loss": best_loss,
        "validation_metrics": _metrics(validation_responses, predicted, outputs),
    }
    example = torch.zeros((2, training_inputs.shape[1]), dtype=torch.float32)
    archive = torch.jit.trace(model, example)
    torch.jit.save(archive, output_path, _extra_files={"metadata.json": json.dumps(metadata)})
    report_path = output_path.with_suffix(".validation.json")
    report_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="Exact Thermochimica training CSV")
    parser.add_argument(
        "--validation-data",
        type=Path,
        help="Disjoint exact validation CSV used for early stopping and support calibration",
    )
    parser.add_argument("--spec", type=Path, required=True, help="Training and archive JSON specification")
    parser.add_argument("--output", type=Path, required=True, help="Output TorchScript archive")
    arguments = parser.parse_args()
    metadata = train(
        arguments.data, arguments.spec, arguments.output, arguments.validation_data
    )
    print(json.dumps({"archive": str(arguments.output), "validation": metadata["validation_metrics"]}))


if __name__ == "__main__":
    main()
