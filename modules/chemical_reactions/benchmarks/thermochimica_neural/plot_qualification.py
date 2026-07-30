#!/usr/bin/env python3
"""Create qualification figures from an external neural benchmark work directory."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PHASE_COLUMNS = [
    ("BCC", "bcc_amount"),
    ("FCC", "fcc_amount"),
    ("HCP", "hcp_amount"),
    ("liquid", "liquid_amount"),
    ("sigma", "sigma_amount"),
]


def _latest_sample(directory: Path, prefix: str) -> Path | None:
    matches = sorted(directory.glob(prefix + "_samples_*.csv"))
    return matches[-1] if matches else None


def _save(figure: plt.Figure, destination: Path) -> list[Path]:
    paths = []
    for suffix in (".pdf", ".png"):
        path = destination.with_suffix(suffix)
        figure.savefig(path, bbox_inches="tight", dpi=200)
        paths.append(path)
    plt.close(figure)
    return paths


def _fe_cr_phase_map(work: Path, output: Path) -> list[Path]:
    table = _latest_sample(work / "fe_cr_multiphase", "test_exact")
    if table is None:
        return []
    data = np.genfromtxt(table, delimiter=",", names=True)
    signatures = []
    for row in range(len(data)):
        active = [
            label for label, column in PHASE_COLUMNS if float(data[column][row]) > 1e-8
        ]
        signatures.append("+".join(active) or "untracked")
    labels = sorted(set(signatures))
    colors = {label: index for index, label in enumerate(labels)}
    values = np.asarray([colors[label] for label in signatures])

    figure, axis = plt.subplots(figsize=(7.0, 4.5))
    axis.scatter(data["Cr"], data["temperature"], c=values, cmap="tab20", s=16)
    for label, color in colors.items():
        axis.scatter([], [], c=[plt.get_cmap("tab20")(color / max(1, len(labels) - 1))], label=label)
    axis.set_xlabel("Cr mole fraction")
    axis.set_ylabel("Temperature [K]")
    axis.set_title("Exact Fe-Cr phase assemblage")
    axis.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    return _save(figure, output / "fe_cr_phase_map")


def _element_scaling(work: Path, output: Path) -> list[Path]:
    path = work / "element_scaling_summary.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    fixed = sorted(
        (row for row in rows if row["fixed_cost"].lower() == "true"),
        key=lambda row: int(row["element_count"]),
    )
    if not fixed:
        return []
    elements = np.asarray([int(row["element_count"]) for row in fixed])
    exact = np.asarray([float(row["exact_worker_time_mean"]) for row in fixed])
    neural = np.asarray([float(row["neural_worker_time_mean"]) for row in fixed])
    prefixes = np.asarray(
        [
            float(row["smallest_passing_prefix"])
            if row["smallest_passing_prefix"] not in ("", "None")
            else np.nan
            for row in fixed
        ]
    )

    figure, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
    axes[0].plot(elements, exact, "o-", label="exact")
    axes[0].plot(elements, neural, "s-", label="guarded neural")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Configured elements")
    axes[0].set_ylabel("Mean worker time [s]")
    axes[0].legend(frameon=False)
    axes[1].plot(elements, prefixes, "o-")
    axes[1].set_yscale("log", base=2)
    axes[1].set_xlabel("Configured elements")
    axes[1].set_ylabel("Smallest passing training prefix")
    figure.suptitle("Element-count scaling")
    return _save(figure, output / "element_scaling")


def _read_numeric_table(path: Path) -> dict[str, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {
        name: np.asarray([float(row[name]) for row in rows])
        for name in (rows[0] if rows else {})
    }


def _first_field_size(radius: np.ndarray, axial: np.ndarray) -> int:
    for row in range(1, len(radius)):
        if radius[row] == radius[0] and axial[row] == axial[0]:
            return row
    return len(radius)


def _msfr_fields(work: Path, output: Path) -> list[Path]:
    case = work / "msfr_ns"
    exact_path = case / "test_exact.csv"
    neural_path = case / "test_neural.csv"
    if not exact_path.exists() or not neural_path.exists():
        return []
    exact = _read_numeric_table(exact_path)
    neural = _read_numeric_table(neural_path)
    size = _first_field_size(exact["radius"], exact["axial_position"])
    radius = exact["radius"][:size]
    axial = exact["axial_position"][:size]
    exact_f = exact["f_potential"][:size]
    error_f = np.abs(neural["f_potential"][:size] - exact_f)
    iodine_gas = exact["i_in_gas"][:size]

    figure, axes = plt.subplots(1, 3, figsize=(12.0, 3.8), constrained_layout=True)
    panels = (
        (exact_f, "Exact fluorine potential", "viridis"),
        (error_f, "Absolute neural replay error", "magma"),
        (iodine_gas, "Exact iodine fraction in gas", "viridis"),
    )
    for axis, (values, title, color_map) in zip(axes, panels):
        image = axis.scatter(radius, axial, c=values, cmap=color_map, marker="s", s=25)
        axis.set_xlabel("Radius [m]")
        axis.set_ylabel("Axial position [m]")
        axis.set_title(title)
        figure.colorbar(image, ax=axis)
    return _save(figure, output / "msfr_field_comparison")


def _iodine_inventory(work: Path, output: Path) -> list[Path]:
    case = work / "msfr_ns"
    pattern = re.compile(r"test_(?P<field>[0-9]+)_(?P<state>fresh|depleted)_(?P<mode>exact|neural)\.csv")
    values = {}
    for path in case.glob("test_*_*.csv"):
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        table = _read_numeric_table(path)
        if "integrated_iodine_gas_inventory" not in table:
            continue
        key = (
            int(match.group("field")),
            match.group("state"),
            match.group("mode"),
        )
        values[key] = float(table["integrated_iodine_gas_inventory"][-1])
    groups = sorted({(field, state) for field, state, _ in values})
    if not groups or any((*group, mode) not in values for group in groups for mode in ("exact", "neural")):
        return []
    locations = np.arange(len(groups))
    width = 0.38
    figure, axis = plt.subplots(figsize=(max(6.0, 1.2 * len(groups)), 4.0))
    axis.bar(
        locations - width / 2,
        [values[(*group, "exact")] for group in groups],
        width,
        label="exact",
    )
    axis.bar(
        locations + width / 2,
        [values[(*group, "neural")] for group in groups],
        width,
        label="guarded neural",
    )
    axis.set_xticks(locations, [f"field {field}\n{state}" for field, state in groups])
    axis.set_ylabel("Integrated iodine gas inventory")
    axis.set_title("MSFR iodine inventory comparison")
    axis.legend(frameon=False)
    return _save(figure, output / "msfr_iodine_inventory")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    arguments = parser.parse_args()
    output = arguments.output_dir or arguments.workdir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    written = []
    written.extend(_fe_cr_phase_map(arguments.workdir, output))
    written.extend(_element_scaling(arguments.workdir, output))
    written.extend(_msfr_fields(arguments.workdir, output))
    written.extend(_iodine_inventory(arguments.workdir, output))
    print(json.dumps({"figures": [str(path) for path in written]}, indent=2))


if __name__ == "__main__":
    main()
