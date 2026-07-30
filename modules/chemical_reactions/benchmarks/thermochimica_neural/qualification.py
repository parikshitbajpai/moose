#!/usr/bin/env python3
"""Run reproducible neural-surrogate qualification studies."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import torch

from train_thermochimica_nn import _canonical_data, _read_csv, train


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEFAULT_APP = ROOT / "modules/chemical_reactions/chemical_reactions-opt"
DEFAULT_COMBINED_APP = ROOT / "modules/combined/combined-opt"
DATABASE = ROOT / "modules/chemical_reactions/benchmarks/thermochimica_adaptive/MSDTC_41_fluorides.dat"
MSFR_COMPOSITIONS = HERE / "msfr_compositions.csv"
MSFR_ELEMENTS = ["F", "Li", "U", "Th", "Ni", "Nd", "Ce", "La", "Cs", "I"]
MOOSE_THREADS = int(os.environ.get("TC_NN_THREADS", "1"))
if MOOSE_THREADS < 1:
    raise ValueError("TC_NN_THREADS must be a positive integer")

ELEMENT_SETS = {
    2: ["Li", "F"],
    5: ["Li", "Be", "F", "Zr", "U"],
    9: ["Li", "Be", "F", "Zr", "U", "Nd", "Ce", "La", "Cs"],
    13: ["Li", "Be", "F", "Zr", "U", "Nd", "Ce", "La", "Cs", "I", "Pu", "K", "Sr"],
    17: [
        "Li",
        "Be",
        "F",
        "Zr",
        "U",
        "Nd",
        "Ce",
        "La",
        "Cs",
        "I",
        "Pu",
        "K",
        "Sr",
        "Ba",
        "Pr",
        "Th",
        "Y",
    ],
    22: [
        "Li",
        "Be",
        "F",
        "Zr",
        "U",
        "Nd",
        "Ce",
        "La",
        "Cs",
        "I",
        "Pu",
        "K",
        "Sr",
        "Ba",
        "Pr",
        "Th",
        "Y",
        "Ni",
        "Fe",
        "Cr",
        "Na",
        "Xe",
    ],
}
ELEMENT_UNION = ELEMENT_SETS[22]
SCALING_OUTPUTS = [
    "f_potential",
    "li_potential",
    "gas_amount",
    "gas_fraction",
    "msfl_amount",
    "msfl_fraction",
    "lif_fraction",
    "system_gibbs",
    "fli_vapor_pressure",
]
TELEMETRY = re.compile(r"ThermochimicaData '[^']+': (?P<body>.+)")
MEMORY_REPORT = re.compile(r"\[\s*(?P<megabytes>[0-9.]+) MB\]")
TELEMETRY_COUNTERS = (
    "states",
    "exact_solves",
    "surrogate_hits",
    "audits",
    "audit_failures",
    "neural_batches",
    "neural_out_of_bounds",
    "neural_support_rejections",
    "neural_phase_rejections",
    "neural_disabled_workers",
)
TELEMETRY_TIMES = ("neural_inference_time", "worker_solve_time")
MSFR_PHASES = [
    ("solid_fli", "FLi_LiF_FM3M_No.225(s)"),
    ("msfl", "MSFL"),
    ("ni_solid", "Ni_fcc(s)"),
    ("u_solid", "U_S1(s)"),
    ("gas", "gas_ideal"),
]
MSFR_SPECIES = [
    ("msfl_cef3", "MSFL", "CeF3"),
    ("msfl_cei3", "MSFL", "CeI3"),
    ("msfl_csf", "MSFL", "CsF"),
    ("msfl_csi", "MSFL", "CsI"),
    ("msfl_laf3", "MSFL", "LaF3"),
    ("msfl_lai3", "MSFL", "LaI3"),
    ("msfl_lif", "MSFL", "LiF"),
    ("msfl_lii", "MSFL", "LiI"),
    ("msfl_ndf3", "MSFL", "NdF3"),
    ("msfl_ndi3", "MSFL", "NdI3"),
    ("msfl_nif2", "MSFL", "NiF2"),
    ("msfl_nii2", "MSFL", "NiI2"),
    ("msfl_thf4", "MSFL", "ThF4"),
    ("msfl_thi4", "MSFL", "ThI4"),
    ("msfl_uf3", "MSFL", "UF3"),
    ("msfl_u7f4", "MSFL", "U[CN=VII]F4"),
    ("msfl_u7i4", "MSFL", "U[CN=VII]I4"),
    ("msfl_u6f4", "MSFL", "U[CN=VI]F4"),
    ("msfl_u6i4", "MSFL", "U[CN=VI]I4"),
    ("msfl_u2f8", "MSFL", "U[Dimer]F8"),
    ("msfl_u2i8", "MSFL", "U[Dimer]I8"),
    ("gas_i", "gas_ideal", "I"),
    ("gas_i2", "gas_ideal", "I2"),
    ("gas_uf5", "gas_ideal", "UF5"),
    ("gas_uf6", "gas_ideal", "UF6"),
]
MSFR_VAPORS = [
    ("i_vapor_pressure", "I"),
    ("i2_vapor_pressure", "I2"),
    ("uf5_vapor_pressure", "UF5"),
    ("uf6_vapor_pressure", "UF6"),
]


def _telemetry_totals(bodies: list[str]) -> dict:
    totals = {field: 0 for field in TELEMETRY_COUNTERS}
    totals.update({field: 0.0 for field in TELEMETRY_TIMES})
    totals.update(
        {
            "phase_rejections": 0,
            "geometry_rejections": 0,
            "error_rejections": 0,
            "invariant_rejections": 0,
            "invalid_state_rejections": 0,
        }
    )
    for body in bodies:
        for field in TELEMETRY_COUNTERS:
            match = re.search(rf"(?:^|, ){field}=([0-9]+)", body)
            if match:
                totals[field] += int(match.group(1))
        for field in TELEMETRY_TIMES:
            match = re.search(
                rf"(?:^|, ){field}=([0-9.eE+-]+) s", body
            )
            if match:
                totals[field] += float(match.group(1))
        rejections = re.search(
            r"rejections=\(phase:([0-9]+),geometry:([0-9]+),error:([0-9]+),"
            r"invariant:([0-9]+),invalid_state:([0-9]+)\)",
            body,
        )
        if rejections:
            for field, value in zip(
                (
                    "phase_rejections",
                    "geometry_rejections",
                    "error_rejections",
                    "invariant_rejections",
                    "invalid_state_rejections",
                ),
                rejections.groups(),
            ):
                totals[field] += int(value)
    return totals


def _run(
    app: Path,
    arguments: list[str],
    log: Path,
    timeout: int | None = None,
    allow_timeout: bool = False,
) -> dict:
    start = time.perf_counter()
    command = [str(app), f"--n-threads={MOOSE_THREADS}", *arguments]
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        wall_time = time.perf_counter() - start
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        log.write_text(output, encoding="utf-8")
        if not allow_timeout:
            raise
        telemetry = [match.group("body") for match in TELEMETRY.finditer(output)]
        return {
            "wall_time": wall_time,
            "timed_out": True,
            "peak_reported_rss_mb": None,
            "telemetry": telemetry,
            "telemetry_totals": _telemetry_totals(telemetry),
            "log": str(log),
        }
    wall_time = time.perf_counter() - start
    log.write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode, command, output=process.stdout
        )
    telemetry = [match.group("body") for match in TELEMETRY.finditer(process.stdout)]
    memory = [float(match.group("megabytes")) for match in MEMORY_REPORT.finditer(process.stdout)]
    return {
        "wall_time": wall_time,
        "timed_out": False,
        "peak_reported_rss_mb": max(memory) if memory else None,
        "telemetry": telemetry,
        "telemetry_totals": _telemetry_totals(telemetry),
        "log": str(log),
    }


def _timing_summary(runs: list[dict]) -> dict:
    def summarize(values: list[float]) -> dict:
        array = np.asarray(values, dtype=np.float64)
        standard_deviation = float(array.std(ddof=1)) if len(array) > 1 else 0.0
        return {
            "repetitions": len(array),
            "mean": float(array.mean()),
            "median": float(np.median(array)),
            "standard_deviation": standard_deviation,
            "confidence_95_half_width": (
                1.96 * standard_deviation / np.sqrt(len(array))
                if len(array) > 1
                else None
            ),
        }

    return {
        "wall_time": summarize([run["wall_time"] for run in runs]),
        "worker_solve_time": summarize(
            [run["telemetry_totals"]["worker_solve_time"] for run in runs]
        ),
        "peak_reported_rss_mb": (
            max(
                run["peak_reported_rss_mb"]
                for run in runs
                if run["peak_reported_rss_mb"] is not None
            )
            if any(run["peak_reported_rss_mb"] is not None for run in runs)
            else None
        ),
    }


def _sample_file(base: Path) -> Path:
    matches = sorted(base.parent.glob(base.name + "_samples_*.csv"))
    if not matches:
        raise FileNotFoundError(f"No ElementValueSampler CSV was produced for {base}")
    return matches[-1]


def _write_state_table(path: Path, count: int, seed: int) -> None:
    engine = torch.quasirandom.SobolEngine(2 + len(ELEMENT_UNION), scramble=True, seed=seed)
    samples = engine.draw(count).numpy().astype(np.float64)
    with path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = ["x", "temperature", "pressure", *ELEMENT_UNION]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row, sample in enumerate(samples):
            values = {
                "x": row + 0.5,
                "temperature": 850.0 + 300.0 * sample[0],
                "pressure": 1.0 + 2.0 * sample[1],
            }
            for column, element in enumerate(ELEMENT_UNION):
                coordinate = sample[2 + column]
                if element == "Li":
                    values[element] = 1.0 * (1.0 + 0.002 * (2.0 * coordinate - 1.0))
                elif element == "F":
                    values[element] = 1.0 * (1.0 - 0.002 * (2.0 * coordinate - 1.0))
                else:
                    values[element] = 1e-6 * 2.0 ** (2.0 * coordinate - 1.0)
            writer.writerow(values)


def _read_msfr_compositions() -> tuple[dict[str, float], dict[str, float]]:
    with MSFR_COMPOSITIONS.open(newline="", encoding="utf-8") as stream:
        rows = {row["state"]: row for row in csv.DictReader(stream)}
    fresh = {element: float(rows["fresh_proxy"][element]) for element in MSFR_ELEMENTS}
    depleted = {element: float(rows["depleted"][element]) for element in MSFR_ELEMENTS}
    return fresh, depleted


def _write_msfr_state_table(path: Path, count: int, seed: int) -> None:
    fresh, depleted = _read_msfr_compositions()
    engine = torch.quasirandom.SobolEngine(5, scramble=True, seed=seed)
    samples = engine.draw(count).numpy().astype(np.float64)
    with path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "x",
            "temperature",
            "pressure",
            "depletion_fraction",
            "redox_factor",
            "nickel_factor",
            *MSFR_ELEMENTS,
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row, sample in enumerate(samples):
            depletion = sample[2]
            redox = 0.95 + 0.10 * sample[3]
            nickel = 0.5 + 1.5 * sample[4]
            composition = {
                element: (1.0 - depletion) * fresh[element] + depletion * depleted[element]
                for element in MSFR_ELEMENTS
            }
            composition["F"] *= redox
            composition["Ni"] *= nickel
            total = sum(composition.values())
            composition = {element: value / total for element, value in composition.items()}
            writer.writerow(
                {
                    "x": row + 0.5,
                    "temperature": 850.0 + 300.0 * sample[0],
                    "pressure": 1.0 + 2.0 * sample[1],
                    "depletion_fraction": depletion,
                    "redox_factor": redox,
                    "nickel_factor": nickel,
                    **composition,
                }
            )


def _decode_exodus_names(array: np.ndarray) -> list[str]:
    return [
        b"".join(row.tolist()).decode("utf-8").rstrip("\x00 ")
        for row in np.asarray(array)
    ]


def _discover_active_outputs(
    exodus: Path, threshold: float = 1e-10, ignored_names: set[str] | None = None
) -> dict:
    from scipy.io import netcdf_file

    with netcdf_file(exodus, "r", mmap=False) as database:
        names = _decode_exodus_names(database.variables["name_elem_var"].data)
        values = {}
        for index, name in enumerate(names, start=1):
            block_values = [
                np.asarray(variable.data[-1], dtype=np.float64)
                for key, variable in database.variables.items()
                if key.startswith(f"vals_elem_var{index}eb")
            ]
            if block_values:
                values[name] = np.concatenate(block_values)

    reserved = {"temperature", "pressure", "system_gibbs", *MSFR_ELEMENTS}
    if ignored_names:
        reserved.update(ignored_names)
    phase_names = [
        name
        for name in names
        if ":" not in name and name not in reserved and name in values
    ]
    active_phases = sorted(
        name for name in phase_names if np.max(np.abs(values[name])) > threshold
    )
    species_names = [
        name
        for name in names
        if name.count(":") == 1 and not name.startswith(("mu:", "vp:", "ep:")) and name in values
    ]
    active_species = sorted(
        name for name in species_names if np.max(np.abs(values[name])) > threshold
    )
    phase_signatures = []
    if active_phases:
        for row in range(len(values[active_phases[0]])):
            phase_signatures.append(
                tuple(phase for phase in active_phases if values[phase][row] > threshold)
            )
    assemblages = {}
    for signature in phase_signatures:
        label = "+".join(signature) or "none"
        assemblages[label] = assemblages.get(label, 0) + 1
    qualifying_states = sum(
        "MSFL" in signature and any(phase not in ("MSFL", "gas_ideal") for phase in signature)
        for signature in phase_signatures
    )
    return {
        "threshold": threshold,
        "active_phases": active_phases,
        "active_species": active_species,
        "assemblages": assemblages,
        "msfl_plus_nongas_states": qualifying_states,
        "qualified": qualifying_states > 0,
    }


def _msfr_output_spec() -> tuple[list[dict], list[dict]]:
    outputs = []
    phase_gates = []
    for prefix, phase in MSFR_PHASES:
        amount = f"{prefix}_amount"
        fraction = f"{prefix}_fraction"
        outputs.extend(
            [
                {
                    "type": "phase",
                    "variable": amount,
                    "phase": phase,
                    "extensive": True,
                    "nonnegative": True,
                    "fraction": False,
                    "absolute_tolerance": 1e-10,
                    "relative_tolerance": 0.01,
                    "transform": {"kind": "log1p", "scale": 1e-10},
                },
                {
                    "type": "phase",
                    "variable": fraction,
                    "phase": phase,
                    "extensive": False,
                    "nonnegative": True,
                    "fraction": True,
                    "absolute_tolerance": 1e-3,
                    "relative_tolerance": 0.0,
                    "transform": {"kind": "log1p", "scale": 1e-8},
                },
            ]
        )
        phase_gates.append(
            {"phase": phase, "amount_variable": amount, "presence_threshold": 1e-10}
        )
    for variable, phase, species in MSFR_SPECIES:
        outputs.append(
            {
                "type": "species",
                "variable": variable,
                "phase": phase,
                "species": species,
                "extensive": True,
                "nonnegative": True,
                "fraction": False,
                "absolute_tolerance": 1e-10,
                "relative_tolerance": 0.01,
                "transform": {"kind": "log1p", "scale": 1e-10},
            }
        )
    for element in MSFR_ELEMENTS:
        outputs.append(
            {
                "type": "element_potential",
                "variable": f"{element.lower()}_potential",
                "element": element,
                "extensive": False,
                "nonnegative": False,
                "fraction": False,
                "absolute_tolerance": 1.0,
                "relative_tolerance": 1e-3,
            }
        )
    for variable, species in MSFR_VAPORS:
        outputs.append(
            {
                "type": "vapor_pressure",
                "variable": variable,
                "phase": "gas_ideal",
                "species": species,
                "extensive": False,
                "nonnegative": True,
                "fraction": False,
                "absolute_tolerance": 1e-12,
                "relative_tolerance": 0.01,
                "materiality_floor": 1e-12,
                "transform": {"kind": "log1p", "scale": 1e-12},
            }
        )
    invariant_groups = [
        {
            "name": "complete_phase_fraction_sum",
            "variables": [f"{prefix}_fraction" for prefix, _ in MSFR_PHASES],
            "target": 1.0,
            "tolerance": 1e-3,
        }
    ]
    for element in MSFR_ELEMENTS:
        variables = []
        for prefix, phase in MSFR_PHASES:
            variable = f"{element.lower()}_in_{prefix}"
            variables.append(variable)
            outputs.append(
                {
                    "type": "element_distribution",
                    "variable": variable,
                    "phase": phase,
                    "element": element,
                    "extensive": False,
                    "nonnegative": True,
                    "fraction": True,
                    "absolute_tolerance": 1e-3,
                    "relative_tolerance": 0.0,
                    "transform": {"kind": "log1p", "scale": 1e-8},
                }
            )
        invariant_groups.append(
            {
                "name": f"complete_{element.lower()}_distribution_sum",
                "variables": variables,
                "target": 1.0,
                "tolerance": 1e-3,
            }
        )
    outputs.extend(
        [
            {
                "type": "element_distribution",
                "variable": "i_amount_in_gas",
                "phase": "gas_ideal",
                "element": "I",
                "extensive": True,
                "nonnegative": True,
                "fraction": False,
                "absolute_tolerance": 1e-10,
                "relative_tolerance": 0.01,
                "transform": {"kind": "log1p", "scale": 1e-10},
            },
            {
                "type": "system_gibbs",
                "variable": "system_gibbs",
                "extensive": True,
                "nonnegative": False,
                "fraction": False,
                "absolute_tolerance": 1.0,
                "relative_tolerance": 1e-3,
            },
        ]
    )
    return outputs, invariant_groups


def _write_exodus_table(exodus_files: list[Path], destination: Path, output_names: list[str]) -> None:
    from scipy.io import netcdf_file

    fieldnames = [
        "radius",
        "axial_position",
        "temperature",
        "pressure",
        *MSFR_ELEMENTS,
        *output_names,
    ]
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for exodus in exodus_files:
            with netcdf_file(exodus, "r", mmap=False) as database:
                names = _decode_exodus_names(database.variables["name_elem_var"].data)
                values = {}
                for index, name in enumerate(names, start=1):
                    blocks = [
                        np.asarray(variable.data[-1], dtype=np.float64)
                        for key, variable in database.variables.items()
                        if key.startswith(f"vals_elem_var{index}eb")
                    ]
                    if blocks:
                        values[name] = np.concatenate(blocks)
            missing = [name for name in fieldnames if name not in values]
            if missing:
                raise ValueError(f"{exodus} is missing replay variables: {missing}")
            for row in range(len(values[fieldnames[0]])):
                writer.writerow({name: values[name][row] for name in fieldnames})


def _interpolated_msfr_composition(fraction: float) -> dict[str, float]:
    fresh, depleted = _read_msfr_compositions()
    return {
        element: (1.0 - fraction) * fresh[element] + fraction * depleted[element]
        for element in MSFR_ELEMENTS
    }


def _replay_arguments(
    flow_file: Path,
    base: Path,
    composition: dict[str, float],
    archive: Path | None = None,
    discover_outputs: bool = False,
) -> list[str]:
    arguments = [
        "-i",
        str(HERE / "msfr_replay.i"),
        f"flow_file={flow_file}",
        f"Outputs/file_base={base}",
    ]
    arguments.extend(f"{element}_value={composition[element]:.17g}" for element in MSFR_ELEMENTS)
    if discover_outputs:
        arguments.extend(
            [
                "ChemicalComposition/thermo/output_phases=ALL",
                "ChemicalComposition/thermo/output_species=ALL",
                "ChemicalComposition/thermo/species_output_unit=moles",
            ]
        )
    if archive is not None:
        arguments.extend(
            [
                "ChemicalComposition/thermo/acceleration=adaptive",
                "ChemicalComposition/thermo/surrogate_model=neural",
                f"ChemicalComposition/thermo/surrogate_archive={archive}",
            ]
        )
    return arguments


def _copy_prefix(source: Path, destination: Path, rows: int) -> None:
    with source.open(newline="", encoding="utf-8") as input_stream:
        reader = csv.DictReader(input_stream)
        selected = []
        for index, row in enumerate(reader):
            if index == rows:
                break
            selected.append(row)
        fieldnames = reader.fieldnames
    if fieldnames is None or len(selected) != rows:
        raise ValueError(f"{source} does not contain {rows} rows")
    with destination.open("w", newline="", encoding="utf-8") as output_stream:
        writer = csv.DictWriter(output_stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)


def _exact_table(
    app: Path,
    work: Path,
    label: str,
    elements: list[str],
    count: int,
    seed: int,
    timeout: int | None = None,
) -> tuple[Path, dict]:
    states = work / f"{label}_states.csv"
    _write_state_table(states, count, seed)
    base = work / f"{label}_exact"
    run = _run(
        app,
        [
            "--allow-unused",
            "-i",
            str(HERE / "element_scaling.i"),
            f"state_file={states}",
            f"state_count={count}",
            f"ChemicalComposition/thermo/elements={' '.join(elements)}",
            "ChemicalComposition/thermo/acceleration=exact",
            f"Outputs/file_base={base}",
        ],
        work / f"{label}_exact.log",
        timeout,
    )
    return _sample_file(base), run


def _array_metrics(
    expected: np.ndarray,
    predicted: np.ndarray,
    outputs: list[dict],
    mask: np.ndarray | None = None,
) -> dict:
    if expected.shape != predicted.shape or expected.shape[1] != len(outputs):
        raise ValueError("Thermochemical metric arrays have inconsistent shapes")
    if mask is None:
        mask = np.ones(expected.shape[0], dtype=bool)
    if not np.any(mask):
        return {
            output["variable"]: {
                "rows": 0,
                "max_absolute_error": None,
                "max_relative_error": None,
                "rmse": None,
                "accepted_fraction": None,
                **(
                    {"max_decade_error_above_floor": None}
                    if output["type"] == "vapor_pressure"
                    else {}
                ),
            }
            for output in outputs
        }

    metrics = {}
    for column, output in enumerate(outputs):
        reference = expected[mask, column]
        prediction = predicted[mask, column]
        errors = np.abs(reference - prediction)
        scales = np.maximum(np.abs(reference), np.abs(prediction))
        tolerance = float(output.get("absolute_tolerance", 0.0)) + float(
            output.get("relative_tolerance", 1e-3)
        ) * scales
        metric = {
            "rows": int(mask.sum()),
            "max_absolute_error": float(errors.max()),
            "max_relative_error": float(
                np.max(errors / np.maximum(scales, np.finfo(np.float64).tiny))
            ),
            "rmse": float(np.sqrt(np.mean(np.square(errors)))),
            "accepted_fraction": float(np.mean(errors <= tolerance)),
        }
        if output["type"] == "vapor_pressure":
            floor = float(
                output.get(
                    "materiality_floor", output.get("absolute_tolerance", 0.0)
                )
            )
            material = reference > floor
            if np.any(material):
                positive_prediction = np.maximum(
                    prediction[material], np.finfo(np.float64).tiny
                )
                metric["max_decade_error_above_floor"] = float(
                    np.max(
                        np.abs(
                            np.log10(positive_prediction)
                            - np.log10(reference[material])
                        )
                    )
                )
            else:
                metric["max_decade_error_above_floor"] = None
        metrics[output["variable"]] = metric
    return metrics


def _metrics_pass(metrics: dict) -> bool:
    for metric in metrics.values():
        if metric["accepted_fraction"] != 1.0:
            return False
        decade_error = metric.get("max_decade_error_above_floor")
        if decade_error is not None and decade_error > 0.1:
            return False
    return True


def _archive_evaluation(exact_path: Path, archive: Path, specification: dict, metadata: dict) -> dict:
    inputs, expected = _canonical_data(_read_csv(exact_path), specification)
    model = torch.jit.load(str(archive), map_location="cpu")
    with torch.inference_mode():
        raw = (
            model(torch.tensor(inputs, dtype=torch.float32))
            .cpu()
            .numpy()
            .astype(np.float64)
        )
    outputs = specification["outputs"]
    predicted = raw[:, : len(outputs)]
    accepted = np.ones(len(inputs), dtype=bool)
    rejection_reason = np.full(len(inputs), "", dtype=object)

    lower = np.asarray(metadata["input_lower_bounds"])
    upper = np.asarray(metadata["input_upper_bounds"])
    bounded = np.all(np.isfinite(inputs) & (inputs >= lower) & (inputs <= upper), axis=1)
    rejection_reason[~bounded] = "bounds"
    accepted &= bounded

    scalar_valid = np.all(np.isfinite(predicted), axis=1)
    for column, output in enumerate(outputs):
        if output.get("nonnegative", False):
            scalar_valid &= predicted[:, column] >= 0.0
        if output.get("fraction", False):
            scalar_valid &= predicted[:, column] <= 1.0
    rejected = accepted & ~scalar_valid
    rejection_reason[rejected] = "scalar_invariant"
    accepted &= scalar_valid

    phase_gate = metadata["phase_gate"]
    phase_count = len(phase_gate["phases"])
    phase_offset = metadata["model_output_layout"]["phase_logit_offset"]
    phase_logits = raw[:, phase_offset : phase_offset + phase_count]
    phase_probability = 1.0 / (1.0 + np.exp(-np.clip(phase_logits, -80.0, 80.0)))
    predicted_signature = phase_probability >= 0.5
    exact_signature = np.zeros_like(predicted_signature)
    phase_valid = np.ones(len(inputs), dtype=bool)
    for column, phase in enumerate(phase_gate["phases"]):
        output_index = phase["output_index"]
        threshold = phase["presence_threshold"]
        exact_signature[:, column] = expected[:, output_index] > threshold
        regressed_present = predicted[:, output_index] > threshold
        phase_valid &= (
            np.maximum(phase_probability[:, column], 1.0 - phase_probability[:, column])
            >= phase_gate["confidence_threshold"]
        )
        phase_valid &= predicted_signature[:, column] == regressed_present
    rejected = accepted & ~phase_valid
    rejection_reason[rejected] = "phase"
    accepted &= phase_valid

    support_valid = np.zeros(len(inputs), dtype=bool)
    for assemblage in metadata["support"]["assemblages"]:
        signature = np.asarray(assemblage["signature"], dtype=bool)
        rows = np.all(predicted_signature == signature, axis=1)
        support_valid[rows] = (
            raw[rows, assemblage["distance_index"]] <= assemblage["radius"]
        )
    rejected = accepted & ~support_valid
    rejection_reason[rejected] = "support"
    accepted &= support_valid

    coupled_valid = np.ones(len(inputs), dtype=bool)
    for group in metadata["invariant_groups"]:
        values = predicted[:, group["output_indices"]].sum(axis=1)
        coupled_valid &= np.abs(values - group["target"]) <= group["tolerance"]
    rejected = accepted & ~coupled_valid
    rejection_reason[rejected] = "coupled_invariant"
    accepted &= coupled_valid

    signature_matches = np.all(predicted_signature == exact_signature, axis=1)
    exact_phase_count = exact_signature.sum(axis=1)
    return {
        "rows": len(inputs),
        "accepted_rows": int(accepted.sum()),
        "accepted_fraction": float(accepted.mean()),
        "all_phase_signature_fraction": float(signature_matches.mean()),
        "accepted_phase_signature_fraction": (
            float(signature_matches[accepted].mean()) if np.any(accepted) else None
        ),
        "single_phase_rows": int(np.sum(exact_phase_count <= 1)),
        "multiphase_rows": int(np.sum(exact_phase_count >= 2)),
        "single_phase_accepted_fraction": (
            float(accepted[exact_phase_count <= 1].mean())
            if np.any(exact_phase_count <= 1)
            else None
        ),
        "multiphase_accepted_fraction": (
            float(accepted[exact_phase_count >= 2].mean())
            if np.any(exact_phase_count >= 2)
            else None
        ),
        "rejections": {
            reason: int(np.sum(rejection_reason == reason))
            for reason in (
                "bounds",
                "scalar_invariant",
                "phase",
                "support",
                "coupled_invariant",
            )
        },
        "all_row_metrics": _array_metrics(expected, predicted, outputs),
        "accepted_row_metrics": _array_metrics(expected, predicted, outputs, accepted),
    }


def _comparison_metrics(exact_path: Path, neural_path: Path, outputs: list[dict]) -> dict:
    with exact_path.open(newline="", encoding="utf-8") as stream:
        exact = list(csv.DictReader(stream))
    with neural_path.open(newline="", encoding="utf-8") as stream:
        neural = list(csv.DictReader(stream))
    if len(exact) != len(neural):
        raise ValueError("Exact and neural sample files have different row counts")
    selected = [output for output in outputs if output["variable"] in SCALING_OUTPUTS]
    expected = np.column_stack(
        [[float(row[output["variable"]]) for row in exact] for output in selected]
    )
    predicted = np.column_stack(
        [[float(row[output["variable"]]) for row in neural] for output in selected]
    )
    return _array_metrics(expected, predicted, selected)


def element_scaling(app: Path, work: Path, manifest: dict) -> dict:
    config = manifest["element_scaling"]
    results = []
    for element_count in config["element_counts"]:
        elements = ELEMENT_SETS[element_count]
        case = work / f"elements_{element_count}"
        case.mkdir(parents=True, exist_ok=True)
        maximum = max(config["training_prefixes"])
        training_csv, training_run = _exact_table(
            app, case, "training", elements, maximum, 41
        )
        validation_csv, validation_run = _exact_table(
            app,
            case,
            "validation",
            elements,
            config["validation_samples"],
            141,
        )
        test_csv, test_run = _exact_table(
            app, case, "test", elements, config["test_samples"], 241
        )
        test_runs = [test_run]
        for repetition in range(1, manifest["repetitions"]):
            test_runs.append(
                _run(
                    app,
                    [
                        "--allow-unused",
                        "-i",
                        str(HERE / "element_scaling.i"),
                        f"state_file={case / 'test_states.csv'}",
                        f"state_count={config['test_samples']}",
                        f"ChemicalComposition/thermo/elements={' '.join(elements)}",
                        "ChemicalComposition/thermo/acceleration=exact",
                        "Outputs/csv=false",
                    ],
                    case / f"test_exact_timing_{repetition}.log",
                )
            )
        template = json.loads((HERE / "element_scaling.json").read_text(encoding="utf-8"))
        template["database"] = str(DATABASE)
        template["elements"] = elements
        template["epochs"] = config["epochs"]
        template["patience"] = config["patience"]
        for prefix in config["training_prefixes"]:
            prefix_csv = case / f"training_{prefix}.csv"
            _copy_prefix(training_csv, prefix_csv, prefix)
            specification = case / f"model_{prefix}.json"
            specification.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
            archive = case / f"model_{prefix}.pt"
            start = time.perf_counter()
            metadata = train(prefix_csv, specification, archive, validation_csv)
            training_time = time.perf_counter() - start
            neural_base = case / f"test_neural_{prefix}"
            neural_arguments = [
                "--allow-unused",
                "-i",
                str(HERE / "element_scaling.i"),
                f"state_file={case / 'test_states.csv'}",
                f"state_count={config['test_samples']}",
                f"ChemicalComposition/thermo/elements={' '.join(elements)}",
                "ChemicalComposition/thermo/acceleration=adaptive",
                "ChemicalComposition/thermo/surrogate_model=neural",
                f"ChemicalComposition/thermo/surrogate_archive={archive}",
                f"Outputs/file_base={neural_base}",
            ]
            neural_run = _run(
                app, neural_arguments, case / f"test_neural_{prefix}.log"
            )
            neural_runs = [neural_run]
            for repetition in range(1, manifest["repetitions"]):
                neural_runs.append(
                    _run(
                        app,
                        [*neural_arguments, "Outputs/csv=false"],
                        case / f"test_neural_{prefix}_timing_{repetition}.log",
                    )
                )
            archive_evaluation = _archive_evaluation(
                test_csv, archive, template, metadata
            )
            replay_metrics = _comparison_metrics(
                test_csv, _sample_file(neural_base), template["outputs"]
            )
            passes_all_outputs = (
                _metrics_pass(archive_evaluation["all_row_metrics"])
                and archive_evaluation["all_phase_signature_fraction"] == 1.0
            )
            results.append(
                {
                    "element_count": element_count,
                    "training_samples": prefix,
                    "fixed_cost": prefix == config["fixed_cost_samples"],
                    "exact_generation": {
                        "training": training_run,
                        "validation": validation_run,
                        "test": test_run,
                    },
                    "exact_test_timing": _timing_summary(test_runs),
                    "training_time": training_time,
                    "archive_bytes": archive.stat().st_size,
                    "validation_metrics": metadata["validation_metrics"],
                    "independent_archive_evaluation": archive_evaluation,
                    "guarded_replay_metrics": replay_metrics,
                    "passes_all_outputs": passes_all_outputs,
                    "neural_run": neural_run,
                    "neural_runs": neural_runs,
                    "neural_timing": _timing_summary(neural_runs),
                }
            )
    fixed_accuracy = {}
    for element_count in config["element_counts"]:
        passing = [
            result["training_samples"]
            for result in results
            if result["element_count"] == element_count and result["passes_all_outputs"]
        ]
        fixed_accuracy[str(element_count)] = min(passing) if passing else None
    summary = {
        "study": "element_scaling",
        "tier": manifest["tier"],
        "smallest_passing_prefix": fixed_accuracy,
        "results": results,
    }
    (work / "element_scaling_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (work / "element_scaling_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        fieldnames = [
            "element_count",
            "training_samples",
            "fixed_cost",
            "passes_all_outputs",
            "training_time",
            "archive_bytes",
            "exact_worker_time_mean",
            "neural_worker_time_mean",
            "neural_worker_time_ci95",
            "neural_wall_time_mean",
            "smallest_passing_prefix",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "element_count": result["element_count"],
                    "training_samples": result["training_samples"],
                    "fixed_cost": result["fixed_cost"],
                    "passes_all_outputs": result["passes_all_outputs"],
                    "training_time": result["training_time"],
                    "archive_bytes": result["archive_bytes"],
                    "exact_worker_time_mean": result["exact_test_timing"][
                        "worker_solve_time"
                    ]["mean"],
                    "neural_worker_time_mean": result["neural_timing"][
                        "worker_solve_time"
                    ]["mean"],
                    "neural_worker_time_ci95": result["neural_timing"][
                        "worker_solve_time"
                    ]["confidence_95_half_width"],
                    "neural_wall_time_mean": result["neural_timing"]["wall_time"][
                        "mean"
                    ],
                    "smallest_passing_prefix": fixed_accuracy[
                        str(result["element_count"])
                    ],
                }
            )
    return summary


def element_stress(app: Path, work: Path, manifest: dict) -> dict:
    config = manifest["element_stress"]
    case = work / "elements_22_stress"
    case.mkdir(parents=True, exist_ok=True)
    states = case / "stress_states.csv"
    _write_state_table(states, config["samples"], 641)
    base = case / "stress_exact"
    run = _run(
        app,
        [
            "--allow-unused",
            "-i",
            str(HERE / "element_scaling.i"),
            f"state_file={states}",
            f"state_count={config['samples']}",
            (
                "ChemicalComposition/thermo/elements="
                + " ".join(ELEMENT_SETS[config["element_count"]])
            ),
            "ChemicalComposition/thermo/acceleration=exact",
            f"Outputs/file_base={base}",
        ],
        case / "stress_exact.log",
        config["timeout_seconds"],
        allow_timeout=True,
    )
    sample_files = sorted(base.parent.glob(base.name + "_samples_*.csv"))
    summary = {
        "study": "element_stress",
        "tier": manifest["tier"],
        "element_count": config["element_count"],
        "samples": config["samples"],
        "accuracy_qualification": config["accuracy_qualification"],
        "censored": run["timed_out"],
        "exact_csv": str(sample_files[-1]) if sample_files else None,
        "run": run,
    }
    (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def fe_cr_multiphase(app: Path, work: Path, manifest: dict) -> dict:
    config = manifest["fe_cr"]
    case = work / "fe_cr_multiphase"
    case.mkdir(parents=True, exist_ok=True)
    training_base = case / "training_exact"
    training_run = _run(
        app,
        [
            "-i",
            str(HERE / "fe_cr_multiphase.i"),
            f"Mesh/gen/nx={config['training_grid']}",
            f"Mesh/gen/ny={config['training_grid']}",
            f"Outputs/file_base={training_base}",
        ],
        case / "training_exact.log",
    )
    validation_base = case / "validation_exact"
    validation_run = _run(
        app,
        [
            "-i",
            str(HERE / "fe_cr_multiphase.i"),
            f"Mesh/gen/nx={config['validation_grid']}",
            f"Mesh/gen/ny={config['validation_grid']}",
            f"Outputs/file_base={validation_base}",
        ],
        case / "validation_exact.log",
    )
    test_base = case / "test_exact"
    test_arguments = [
        "-i",
        str(HERE / "fe_cr_multiphase.i"),
        f"Mesh/gen/nx={config['test_grid']}",
        f"Mesh/gen/ny={config['test_grid']}",
        f"Outputs/file_base={test_base}",
    ]
    test_run = _run(app, test_arguments, case / "test_exact.log")
    test_runs = [test_run]
    for repetition in range(1, manifest["repetitions"]):
        test_runs.append(
            _run(
                app,
                [*test_arguments, "Outputs/csv=false"],
                case / f"test_exact_timing_{repetition}.log",
            )
        )
    specification_data = json.loads(
        (HERE / "fe_cr_multiphase.json").read_text(encoding="utf-8")
    )
    specification_data["database"] = str(DATABASE)
    specification_data["epochs"] = config["epochs"]
    specification_data["patience"] = config["patience"]
    specification = case / "model.json"
    specification.write_text(json.dumps(specification_data, indent=2) + "\n", encoding="utf-8")
    archive = case / "model.pt"
    metadata = train(
        _sample_file(training_base), specification, archive, _sample_file(validation_base)
    )
    neural_base = case / "test_neural"
    neural_arguments = [
        "-i",
        str(HERE / "fe_cr_multiphase.i"),
        f"Mesh/gen/nx={config['test_grid']}",
        f"Mesh/gen/ny={config['test_grid']}",
        "ChemicalComposition/thermo/acceleration=adaptive",
        "ChemicalComposition/thermo/surrogate_model=neural",
        f"ChemicalComposition/thermo/surrogate_archive={archive}",
        f"Outputs/file_base={neural_base}",
    ]
    neural_run = _run(app, neural_arguments, case / "test_neural.log")
    neural_runs = [neural_run]
    for repetition in range(1, manifest["repetitions"]):
        neural_runs.append(
            _run(
                app,
                [*neural_arguments, "Outputs/csv=false"],
                case / f"test_neural_timing_{repetition}.log",
            )
        )
    phases = ["bcc_amount", "fcc_amount", "hcp_amount", "liquid_amount", "sigma_amount"]
    test_csv = _sample_file(test_base)
    with test_csv.open(newline="", encoding="utf-8") as stream:
        exact_rows = list(csv.DictReader(stream))
    assemblages = {}
    multiphase_states = 0
    for row in exact_rows:
        signature = tuple(phase for phase in phases if float(row[phase]) > 1e-8)
        assemblages["+".join(signature) or "untracked"] = (
            assemblages.get("+".join(signature) or "untracked", 0) + 1
        )
        multiphase_states += len(signature) >= 2
    required = 50 if manifest["tier"] == "full" else 1
    multiphase_qualified = (
        len(assemblages) >= 2
        and multiphase_states >= required
        and "untracked" not in assemblages
    )
    archive_evaluation = _archive_evaluation(
        test_csv, archive, specification_data, metadata
    )
    surrogate_qualified = (
        archive_evaluation["accepted_rows"] > 0
        and archive_evaluation["accepted_phase_signature_fraction"] == 1.0
        and _metrics_pass(archive_evaluation["accepted_row_metrics"])
        and neural_run["telemetry_totals"]["audit_failures"] == 0
    )
    summary = {
        "study": "fe_cr_multiphase",
        "tier": manifest["tier"],
        "qualified": multiphase_qualified and surrogate_qualified,
        "multiphase_qualified": multiphase_qualified,
        "surrogate_qualified": surrogate_qualified,
        "required_multiphase_states": required,
        "multiphase_states": multiphase_states,
        "assemblages": assemblages,
        "training_run": training_run,
        "validation_run": validation_run,
        "test_run": test_run,
        "test_runs": test_runs,
        "exact_test_timing": _timing_summary(test_runs),
        "neural_run": neural_run,
        "neural_runs": neural_runs,
        "neural_timing": _timing_summary(neural_runs),
        "validation_metrics": metadata["validation_metrics"],
        "independent_archive_evaluation": archive_evaluation,
        "guarded_replay_metrics": _output_metrics(
            test_csv, _sample_file(neural_base), specification_data["outputs"]
        ),
    }
    (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def fluoride_discovery(app: Path, work: Path, manifest: dict) -> dict:
    config = manifest["fluoride_discovery"]
    case = work / "fluoride_discovery"
    case.mkdir(parents=True, exist_ok=True)
    states = case / "states.csv"
    _write_msfr_state_table(states, config["samples"], config["seed"])
    base = case / "exact"
    run = _run(
        app,
        [
            "-i",
            str(HERE / "fluoride_discovery.i"),
            f"state_file={states}",
            f"state_count={config['samples']}",
            f"Outputs/file_base={base}",
        ],
        case / "exact.log",
    )
    discovery = _discover_active_outputs(base.with_suffix(".e"))
    listed_phases = {phase for _, phase in MSFR_PHASES}
    listed_species = {f"{phase}:{species}" for _, phase, species in MSFR_SPECIES}
    unlisted_phases = sorted(set(discovery["active_phases"]) - listed_phases)
    unlisted_species = sorted(set(discovery["active_species"]) - listed_species)
    summary = {
        "study": "fluoride_discovery",
        "tier": manifest["tier"],
        "run": run,
        **discovery,
        "unlisted_phases": unlisted_phases,
        "unlisted_species": unlisted_species,
        "qualified": discovery["qualified"] and not unlisted_phases and not unlisted_species,
    }
    (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _operating_points(count: int, seed: int) -> list[dict[str, float]]:
    engine = torch.quasirandom.SobolEngine(4, scramble=True, seed=seed)
    samples = engine.draw(count).numpy().astype(np.float64)
    return [
        {
            "inlet_temperature": 850.0 + 100.0 * sample[0],
            "flow_scale": 0.8 + 0.4 * sample[1],
            "heat_scale": 0.8 + 0.4 * sample[2],
            "outlet_pressure": 1.5e5 + 1.0e5 * sample[3],
        }
        for sample in samples
    ]


def _run_precursor(
    app: Path, case: Path, label: str, point: dict[str, float], nx: int, ny: int
) -> tuple[Path, dict]:
    base = case / label
    arguments = [
        "-i",
        str(HERE / "msfr_ns_precursor.i"),
        f"nx={nx}",
        f"ny={ny}",
        f"Outputs/file_base={base}",
    ]
    arguments.extend(f"{name}={value:.17g}" for name, value in point.items())
    run = _run(app, arguments, case / f"{label}.log")
    return base.with_suffix(".e"), run


def _output_metrics(exact_path: Path, neural_path: Path, outputs: list[dict]) -> dict:
    with exact_path.open(newline="", encoding="utf-8") as stream:
        exact = list(csv.DictReader(stream))
    with neural_path.open(newline="", encoding="utf-8") as stream:
        neural = list(csv.DictReader(stream))
    if len(exact) != len(neural):
        raise ValueError("Exact and neural replay tables have different row counts")
    expected = np.column_stack(
        [[float(row[output["variable"]]) for row in exact] for output in outputs]
    )
    predicted = np.column_stack(
        [[float(row[output["variable"]]) for row in neural] for output in outputs]
    )
    return _array_metrics(expected, predicted, outputs)


def msfr_ns_study(
    flow_app: Path, replay_app: Path, work: Path, manifest: dict
) -> dict:
    config = manifest["msfr_ns"]
    case = work / "msfr_ns"
    case.mkdir(parents=True, exist_ok=True)
    training_points = _operating_points(config["training_operating_points"], 301)
    validation_points = _operating_points(config["validation_operating_points"], 401)
    if config["test_operating_points"] == 1:
        test_points = [
            {
                "inlet_temperature": 900.0,
                "flow_scale": 1.0,
                "heat_scale": 1.0,
                "outlet_pressure": 2.0e5,
            }
        ]
    else:
        test_points = [
            {
                "inlet_temperature": 900.0,
                "flow_scale": 1.0,
                "heat_scale": 1.0,
                "outlet_pressure": 2.0e5,
            },
            {
                "inlet_temperature": 940.0,
                "flow_scale": 1.15,
                "heat_scale": 1.15,
                "outlet_pressure": 1.7e5,
            },
        ]

    precursor_runs = {"training": [], "validation": [], "test": []}
    training_fields = []
    for index, point in enumerate(training_points):
        field, run = _run_precursor(
            flow_app, case, f"training_field_{index}", point, config["nx"], config["ny"]
        )
        training_fields.append(field)
        precursor_runs["training"].append(run)
    validation_fields = []
    for index, point in enumerate(validation_points):
        field, run = _run_precursor(
            flow_app, case, f"validation_field_{index}", point, config["nx"], config["ny"]
        )
        validation_fields.append(field)
        precursor_runs["validation"].append(run)
    test_fields = []
    for index, point in enumerate(test_points):
        field, run = _run_precursor(
            flow_app, case, f"test_field_{index}", point, config["nx"], config["ny"]
        )
        test_fields.append(field)
        precursor_runs["test"].append(run)

    outputs, invariant_groups = _msfr_output_spec()
    output_names = [output["variable"] for output in outputs]
    training_replays = []
    training_exodus = []
    training_fractions = np.linspace(0.0, 1.0, len(training_fields))
    for index, (field, fraction) in enumerate(zip(training_fields, training_fractions)):
        base = case / f"training_exact_{index}"
        run = _run(
            replay_app,
            _replay_arguments(field, base, _interpolated_msfr_composition(float(fraction))),
            case / f"training_exact_{index}.log",
        )
        training_replays.append(run)
        training_exodus.append(base.with_suffix(".e"))
    validation_replays = []
    validation_exodus = []
    validation_fractions = (np.arange(len(validation_fields)) + 0.5) / len(validation_fields)
    for index, (field, fraction) in enumerate(zip(validation_fields, validation_fractions)):
        base = case / f"validation_exact_{index}"
        run = _run(
            replay_app,
            _replay_arguments(
                field,
                base,
                _interpolated_msfr_composition(float(fraction)),
                discover_outputs=True,
            ),
            case / f"validation_exact_{index}.log",
        )
        validation_replays.append(run)
        validation_exodus.append(base.with_suffix(".e"))

    training_csv = case / "training.csv"
    validation_csv = case / "validation.csv"
    _write_exodus_table(training_exodus, training_csv, output_names)
    _write_exodus_table(validation_exodus, validation_csv, output_names)
    listed_phases = {phase for _, phase in MSFR_PHASES}
    listed_species = {f"{phase}:{species}" for _, phase, species in MSFR_SPECIES}
    validation_discovery = [
        _discover_active_outputs(exodus, ignored_names=set(output_names))
        for exodus in validation_exodus
    ]
    validation_phases = set().union(
        *(set(discovery["active_phases"]) for discovery in validation_discovery)
    )
    validation_species = set().union(
        *(set(discovery["active_species"]) for discovery in validation_discovery)
    )
    unlisted_validation_phases = sorted(validation_phases - listed_phases)
    unlisted_validation_species = sorted(validation_species - listed_species)
    if unlisted_validation_phases or unlisted_validation_species:
        raise ValueError(
            "Validation replay contains outputs absent from the discovery union: "
            f"phases={unlisted_validation_phases}, species={unlisted_validation_species}"
        )
    specification_data = {
        "database": str(DATABASE),
        "temperature_column": "temperature",
        "pressure_column": "pressure",
        "temperature_unit": "K",
        "pressure_unit": "Pa",
        "composition_unit": "moles",
        "elements": MSFR_ELEMENTS,
        "outputs": outputs,
        "phase_gate": {
            "confidence_threshold": 0.99,
            "loss_weight": 0.1,
            "phases": [
                {
                    "phase": phase,
                    "amount_variable": f"{prefix}_amount",
                    "presence_threshold": 1e-10,
                }
                for prefix, phase in MSFR_PHASES
            ],
        },
        "invariant_groups": invariant_groups,
        "support": {"quantile": 0.99, "padding": 1.25},
        "epochs": 600 if manifest["tier"] == "quick" else 3000,
        "patience": 80 if manifest["tier"] == "quick" else 200,
        "learning_rate": 1e-3,
        "seed": 501,
    }
    specification = case / "model.json"
    specification.write_text(json.dumps(specification_data, indent=2) + "\n", encoding="utf-8")
    archive = case / "model.pt"
    start = time.perf_counter()
    metadata = train(training_csv, specification, archive, validation_csv)
    training_time = time.perf_counter() - start

    exact_test_exodus = []
    neural_test_exodus = []
    exact_test_runs = []
    neural_test_runs = []
    held_out_discovery_exodus = []
    held_out_discovery_runs = []
    for field_index, field in enumerate(test_fields):
        for state, fraction in (("fresh", 0.0), ("depleted", 1.0)):
            composition = _interpolated_msfr_composition(fraction)
            exact_base = case / f"test_{field_index}_{state}_exact"
            exact_arguments = _replay_arguments(field, exact_base, composition)
            exact_test_runs.append(
                _run(
                    replay_app,
                    exact_arguments,
                    case / f"test_{field_index}_{state}_exact.log",
                )
            )
            exact_test_exodus.append(exact_base.with_suffix(".e"))
            discovery_base = case / f"test_{field_index}_{state}_discovery"
            held_out_discovery_runs.append(
                _run(
                    replay_app,
                    _replay_arguments(
                        field, discovery_base, composition, discover_outputs=True
                    ),
                    case / f"test_{field_index}_{state}_discovery.log",
                )
            )
            held_out_discovery_exodus.append(discovery_base.with_suffix(".e"))
            for repetition in range(1, manifest["repetitions"]):
                exact_test_runs.append(
                    _run(
                        replay_app,
                        [*exact_arguments, "Outputs/exodus=false", "Outputs/csv=false"],
                        case
                        / f"test_{field_index}_{state}_exact_timing_{repetition}.log",
                    )
                )
            neural_base = case / f"test_{field_index}_{state}_neural"
            neural_arguments = _replay_arguments(
                field, neural_base, composition, archive
            )
            neural_test_runs.append(
                _run(
                    replay_app,
                    neural_arguments,
                    case / f"test_{field_index}_{state}_neural.log",
                )
            )
            neural_test_exodus.append(neural_base.with_suffix(".e"))
            for repetition in range(1, manifest["repetitions"]):
                neural_test_runs.append(
                    _run(
                        replay_app,
                        [*neural_arguments, "Outputs/exodus=false", "Outputs/csv=false"],
                        case
                        / f"test_{field_index}_{state}_neural_timing_{repetition}.log",
                    )
                )

    exact_test_csv = case / "test_exact.csv"
    neural_test_csv = case / "test_neural.csv"
    _write_exodus_table(exact_test_exodus, exact_test_csv, output_names)
    _write_exodus_table(neural_test_exodus, neural_test_csv, output_names)
    guarded_replay_metrics = _output_metrics(
        exact_test_csv, neural_test_csv, outputs
    )
    archive_evaluation = _archive_evaluation(
        exact_test_csv, archive, specification_data, metadata
    )
    held_out_discovery = [
        _discover_active_outputs(exodus, ignored_names=set(output_names))
        for exodus in held_out_discovery_exodus
    ]
    active_phases = set().union(
        *(set(discovery["active_phases"]) for discovery in held_out_discovery)
    )
    active_species = set().union(
        *(set(discovery["active_species"]) for discovery in held_out_discovery)
    )
    unseen_outputs = {
        "active_phases": sorted(active_phases),
        "active_species": sorted(active_species),
        "unlisted_phases": sorted(active_phases - listed_phases),
        "unlisted_species": sorted(active_species - listed_species),
    }
    exact_worker_time = sum(
        run["telemetry_totals"]["worker_solve_time"] for run in exact_test_runs
    )
    neural_worker_time = sum(
        run["telemetry_totals"]["worker_solve_time"] for run in neural_test_runs
    )
    neural_states = sum(
        run["telemetry_totals"]["states"] for run in neural_test_runs
    )
    neural_exact_solves = sum(
        run["telemetry_totals"]["exact_solves"] for run in neural_test_runs
    )
    audit_failures = sum(
        run["telemetry_totals"]["audit_failures"] for run in neural_test_runs
    )
    exact_solve_reduction = (
        1.0 - neural_exact_solves / neural_states if neural_states else 0.0
    )
    worker_speedup = (
        exact_worker_time / neural_worker_time
        if neural_worker_time > 0.0
        else None
    )
    end_to_end_speedup = (
        sum(run["wall_time"] for run in exact_test_runs)
        / sum(run["wall_time"] for run in neural_test_runs)
        if sum(run["wall_time"] for run in neural_test_runs) > 0.0
        else None
    )
    acceptance = {
        "accepted_accuracy": (
            archive_evaluation["accepted_rows"] > 0
            and _metrics_pass(archive_evaluation["accepted_row_metrics"])
        ),
        "phase_signatures": (
            archive_evaluation["accepted_phase_signature_fraction"] == 1.0
        ),
        "unseen_outputs": (
            not unseen_outputs["unlisted_phases"]
            and not unseen_outputs["unlisted_species"]
        ),
        "audit_failures": audit_failures == 0,
        "exact_solve_reduction": exact_solve_reduction >= 0.8,
        "worker_speedup": worker_speedup is not None and worker_speedup >= 2.0,
    }
    summary = {
        "study": "msfr_ns",
        "tier": manifest["tier"],
        "flow_app": str(flow_app),
        "replay_app": str(replay_app),
        "precursor_runs": precursor_runs,
        "training_replays": training_replays,
        "validation_replays": validation_replays,
        "validation_discovery": validation_discovery,
        "training_time": training_time,
        "archive_bytes": archive.stat().st_size,
        "validation_metrics": metadata["validation_metrics"],
        "exact_test_runs": exact_test_runs,
        "neural_test_runs": neural_test_runs,
        "held_out_discovery_runs": held_out_discovery_runs,
        "exact_test_timing": _timing_summary(exact_test_runs),
        "neural_test_timing": _timing_summary(neural_test_runs),
        "independent_archive_evaluation": archive_evaluation,
        "guarded_replay_metrics": guarded_replay_metrics,
        "unseen_output_check": unseen_outputs,
        "exact_solve_reduction": exact_solve_reduction,
        "worker_speedup": worker_speedup,
        "end_to_end_speedup": end_to_end_speedup,
        "acceptance": acceptance,
        "qualified": all(acceptance.values()),
    }
    (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "study", choices=("fe_cr", "elements", "stress", "fluoride", "ns", "all")
    )
    parser.add_argument("--tier", choices=("quick", "full"), default="quick")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    parser.add_argument("--combined-app", type=Path, default=DEFAULT_COMBINED_APP)
    parser.add_argument("--flow-app", type=Path)
    parser.add_argument("--replay-app", type=Path)
    parser.add_argument("--element-count", type=int, choices=tuple(ELEMENT_SETS))
    arguments = parser.parse_args()
    manifest = json.loads(
        (HERE / "manifests" / f"{arguments.tier}.json").read_text(encoding="utf-8")
    )
    arguments.workdir.mkdir(parents=True, exist_ok=True)
    if arguments.element_count is not None:
        manifest["element_scaling"]["element_counts"] = [arguments.element_count]
    summaries = {}
    if arguments.study in ("fe_cr", "all"):
        summaries["fe_cr"] = fe_cr_multiphase(arguments.app, arguments.workdir, manifest)
    if arguments.study in ("elements", "all"):
        summaries["elements"] = element_scaling(arguments.app, arguments.workdir, manifest)
    if arguments.study in ("stress", "all") and "element_stress" in manifest:
        summaries["stress"] = element_stress(arguments.app, arguments.workdir, manifest)
    if arguments.study in ("fluoride", "all"):
        summaries["fluoride"] = fluoride_discovery(arguments.app, arguments.workdir, manifest)
    if arguments.study in ("ns", "all"):
        summaries["ns"] = msfr_ns_study(
            arguments.flow_app or arguments.combined_app,
            arguments.replay_app or arguments.combined_app,
            arguments.workdir,
            manifest,
        )
    (arguments.workdir / "qualification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
