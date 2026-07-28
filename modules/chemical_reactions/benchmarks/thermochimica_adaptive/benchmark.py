#!/usr/bin/env python3
"""Run and analyze the adaptive Thermochimica benchmark suite."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
MANIFESTS = ROOT / "manifests"
PLOT_STYLE = ROOT / "report.mplstyle"

METHOD_LABELS = {
    "exact_gem": "Full GEM",
    "exact": "Full GEM",
    "local_idw": "Adaptive local interpolation",
    "kkt_linear": "Adaptive KKT sensitivity",
}
METHOD_COLORS = {
    "exact_gem": "#000000",
    "local_idw": "#0072B2",
    "kkt_linear": "#E69F00",
}
METHOD_LINESTYLES = {
    "exact_gem": "-",
    "local_idw": "--",
    "kkt_linear": "-.",
}
METHOD_MARKERS = {
    "exact_gem": "o",
    "local_idw": "s",
    "kkt_linear": "^",
}

CASE_FILES = {
    "binary_comparison": CASES / "binary_boundary.i",
    "binary_smooth": CASES / "binary_smooth.i",
    "binary_boundary": CASES / "binary_boundary.i",
    "multielement_fluoride": CASES / "multielement_fluoride.i",
    "multielement_heat_capacity": CASES / "multielement_heat_capacity.i",
    "fluoride_dimension_trace": CASES / "fluoride_dimension_trace.i",
    "lif_excess_f": CASES / "lif_excess_f.i",
    "lif_low_temperature": CASES / "lif_low_temperature.i",
    "flibe_msfl": CASES / "flibe_msfl.i",
}

CASE_DATABASES = {
    "binary_comparison": (
        ROOT.parent.parent / "test/tests/thermochimica/Kaye_NobleMetals.dat",
        "49afab992d4e43522fdb60eda8f875654411523123080553555e12d7cb817829",
    ),
    "binary_smooth": (
        ROOT.parent.parent / "test/tests/thermochimica/Kaye_NobleMetals.dat",
        "49afab992d4e43522fdb60eda8f875654411523123080553555e12d7cb817829",
    ),
    "binary_boundary": (
        ROOT.parent.parent / "test/tests/thermochimica/Kaye_NobleMetals.dat",
        "49afab992d4e43522fdb60eda8f875654411523123080553555e12d7cb817829",
    ),
}
FLUORIDE_DATABASE = (
    ROOT / "MSDTC_41_fluorides.dat",
    "1236d1a57bf0f12eea6e0e20d99747b299b60099fe3655e6ee46da6318704266",
)
for _case in (
    "multielement_fluoride",
    "multielement_heat_capacity",
    "fluoride_dimension_trace",
    "lif_excess_f",
    "lif_low_temperature",
    "flibe_msfl",
):
    CASE_DATABASES[_case] = FLUORIDE_DATABASE

CASE_OUTPUTS = {
    "binary_comparison": [
        "bcc_amount",
        "hcp_amount",
        "bcc_fraction",
        "hcp_fraction",
        "fcc_amount",
        "fcc_fraction",
        "liquid_amount",
        "liquid_fraction",
        "sigma_amount",
        "sigma_fraction",
        "mo_potential",
        "system_gibbs",
    ],
    "binary_smooth": [
        "bcc_amount",
        "hcp_amount",
        "bcc_fraction",
        "hcp_fraction",
        "mo_potential",
        "system_gibbs",
    ],
    "binary_boundary": [
        "bcc_amount",
        "hcp_amount",
        "bcc_fraction",
        "hcp_fraction",
        "fcc_amount",
        "fcc_fraction",
        "liquid_amount",
        "liquid_fraction",
        "sigma_amount",
        "sigma_fraction",
        "mo_potential",
        "system_gibbs",
    ],
    "multielement_fluoride": [
        "msfl_amount",
        "msfl_fraction",
        "gas_amount",
        "gas_fraction",
        "f_potential",
        "system_gibbs",
    ],
    "multielement_heat_capacity": [
        "msfl_amount",
        "msfl_fraction",
        "gas_amount",
        "gas_fraction",
        "f_potential",
        "system_gibbs",
        "system_heat_capacity",
    ],
    "fluoride_dimension_trace": [
        "msfl_amount", "msfl_fraction", "gas_amount", "gas_fraction", "f_potential", "system_gibbs"
    ],
    "lif_excess_f": [
        "msfl_amount", "msfl_fraction", "gas_amount", "gas_fraction", "f_potential", "system_gibbs"
    ],
    "lif_low_temperature": [
        "msfl_amount", "msfl_fraction", "gas_amount", "gas_fraction", "f_potential", "system_gibbs"
    ],
    "flibe_msfl": [
        "msfl_amount", "msfl_fraction", "gas_amount", "gas_fraction", "f_potential", "system_gibbs"
    ],
}

ELEMENT_SETS = {
    2: "Li F",
    5: "Li Be F Zr U",
    9: "Li Be F Zr U Nd Ce La Cs",
    13: "Li Be F Zr U Nd Ce La Cs I Pu K Sr",
    17: "Li Be F Zr U Nd Ce La Cs I Pu K Sr Ba Pr Th Y",
    22: "Li Be F Zr U Nd Ce La Cs I Pu K Sr Ba Pr Th Y Ni Fe Cr Na Xe",
}

INT_FIELDS = [
    "states",
    "batches",
    "exact_solves",
    "gem_iterations",
    "warm_starts",
    "exact_reuse_hits",
    "surrogate_hits",
    "audits",
    "audit_failures",
    "nearest_warm_starts",
    "cold_retries",
    "cache_entries",
    "cache_saturated",
    "sensitivity_successes",
    "sensitivity_failures",
    "sensitivity_condition_rejections",
    "sensitivity_residual_rejections",
    "unsupported_model_rejections",
    "state_restore_failures",
    "complementarity_rejections",
    "linear_retrieves",
    "ellipsoid_growths",
    "ellipsoid_shrinks",
    "sensitivity_bytes",
]
REJECTION_FIELDS = [
    "phase_rejections",
    "geometry_rejections",
    "error_rejections",
    "invariant_rejections",
    "invalid_state_rejections",
]
TIME_FIELDS = ["worker_solve_time", "sensitivity_time", "packing_time", "ipc_time"]

RUN_FIELDS = [
    "run_id",
    "tier",
    "study",
    "case",
    "problem_id",
    "composition_min",
    "composition_max",
    "temporal_displacement",
    "mode",
    "surrogate_model",
    "repetition",
    "stage_index",
    "stage",
    "axis",
    "axis_value",
    "mesh_elements",
    "chemical_elements",
    "relative_tolerance",
    "neighbors",
    "cache_capacity",
    "audit_interval",
    "warm_start",
    "threads",
    "ranks",
    "wall_time",
    "peak_rss_bytes",
] + INT_FIELDS + REJECTION_FIELDS + TIME_FIELDS + [
    "baseline_wall_time",
    "baseline_worker_solve_time",
    "baseline_exact_solves",
    "wall_speedup",
    "worker_speedup",
    "exact_call_reduction",
    "meets_capability_gate",
    "sample_file",
    "log_file",
]

ACCURACY_FIELDS = [
    "run_id",
    "tier",
    "study",
    "case",
    "problem_id",
    "surrogate_model",
    "repetition",
    "axis",
    "axis_value",
    "mesh_elements",
    "chemical_elements",
    "relative_tolerance",
    "output",
    "samples",
    "max_absolute_error",
    "rmse",
    "p95_absolute_error",
    "max_relative_error",
    "p95_relative_error",
    "relative_scale_floor",
    "absolute_tolerance",
    "absolute_tolerance_source",
    "max_normalized_error",
    "p95_normalized_error",
]

FAILURE_FIELDS = [
    "tier",
    "study",
    "case",
    "problem_id",
    "surrogate_model",
    "axis",
    "axis_value",
    "mesh_elements",
    "chemical_elements",
    "threads",
    "ranks",
    "error",
]

TELEMETRY = re.compile(r"ThermochimicaData '[^']+': (?P<body>.+)")
REJECTIONS = re.compile(
    r"rejections=\(phase:(\d+),geometry:(\d+),error:(\d+),"
    r"invariant:(\d+),invalid_state:(\d+)\)"
)


def load_manifest(tier: str) -> dict[str, Any]:
    with (MANIFESTS / f"{tier}.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest.get("studies"), dict):
        raise ValueError(f"Manifest {tier}.json does not define a studies object")
    return manifest


def validate_case_databases(cases: set[str]) -> None:
    """Require the exact database bytes used to qualify each selected benchmark case."""
    checked = set()
    for case in sorted(cases):
        path, expected = CASE_DATABASES[case]
        if path in checked:
            continue
        checked.add(path)
        if not path.is_file():
            raise FileNotFoundError(
                f"Required Thermochimica database is missing: {path}. "
                "Update the benchmark branch and submodules before running."
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"Thermochimica database checksum mismatch for {path}: "
                f"expected {expected}, found {actual}. Restore the file from Git before running."
            )


def slug(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def median(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return statistics.median(finite) if finite else math.nan


def iqr(values: list[float]) -> float:
    finite = sorted(value for value in values if math.isfinite(value))
    if len(finite) < 2:
        return 0.0 if finite else math.nan
    return percentile(finite, 0.75) - percentile(finite, 0.25)


def parse_telemetry(text: str) -> list[dict[str, Any]]:
    stages = []
    for line in text.splitlines():
        match = TELEMETRY.search(line)
        if not match:
            continue
        body = match.group("body")
        record: dict[str, Any] = {}
        for field in INT_FIELDS:
            value = re.search(rf"(?:^|, ){re.escape(field)}=(\d+)", body)
            if not value:
                raise ValueError(f"Missing telemetry field '{field}' in: {line}")
            record[field] = int(value.group(1))
        rejection = REJECTIONS.search(body)
        if not rejection:
            raise ValueError(f"Could not parse rejection counters in: {line}")
        for field, value in zip(REJECTION_FIELDS, rejection.groups()):
            record[field] = int(value)
        for field in TIME_FIELDS:
            value = re.search(rf"{re.escape(field)}=([0-9.eE+-]+) s", body)
            if not value:
                raise ValueError(f"Missing telemetry field '{field}' in: {line}")
            record[field] = float(value.group(1))
        stages.append(record)
    if not stages:
        raise ValueError("The application output did not contain Thermochimica telemetry")
    return stages


def read_samples(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    rows.sort(key=lambda row: (row.get("id", 0.0), row.get("x", 0.0)))
    return rows


def validate_sample_invariants(case: str, rows: list[dict[str, float]]) -> None:
    if not rows:
        raise ValueError(f"{case} did not produce sampled output")
    for index, row in enumerate(rows):
        for output in CASE_OUTPUTS[case]:
            if output not in row or not math.isfinite(row[output]):
                raise ValueError(f"Non-finite or missing {output} at sampled row {index}")
            if output.endswith("_fraction") and not -1e-12 <= row[output] <= 1.0 + 1e-12:
                raise ValueError(f"Fraction {output} is outside [0, 1] at sampled row {index}")
            if output.endswith("_amount") and row[output] < -1e-12:
                raise ValueError(f"Amount {output} is negative at sampled row {index}")


def compare_samples(
    run_id: str,
    tier: str,
    config: dict[str, Any],
    repetition: int,
    exact_path: Path,
    adaptive_path: Path,
    absolute_tolerances: dict[str, float] | None = None,
    absolute_tolerance_source: str = "numerical_precision",
) -> list[dict[str, Any]]:
    exact = read_samples(exact_path)
    adaptive = read_samples(adaptive_path)
    if len(exact) != len(adaptive):
        raise ValueError(f"Sample count differs: exact={len(exact)}, adaptive={len(adaptive)}")
    validate_sample_invariants(config["case"], exact)
    validate_sample_invariants(config["case"], adaptive)
    for exact_row, adaptive_row in zip(exact, adaptive):
        if exact_row.get("id") != adaptive_row.get("id"):
            raise ValueError("Exact and adaptive sample element IDs do not match")

    records = []
    for output in CASE_OUTPUTS[config["case"]]:
        expected = [row[output] for row in exact]
        actual = [row[output] for row in adaptive]
        absolute = [abs(lhs - rhs) for lhs, rhs in zip(expected, actual)]
        scale_floor = 1e-12 * max(max((abs(value) for value in expected), default=0.0), 1.0)
        absolute_tolerance = (absolute_tolerances or {}).get(
            output,
            100.0
            * sys.float_info.epsilon
            * max(max((abs(value) for value in expected), default=0.0), 1.0),
        )
        relative = [
            error / max(abs(value), scale_floor)
            for error, value in zip(absolute, expected)
        ]
        normalized = [
            error
            / (
                absolute_tolerance
                + config["relative_tolerance"] * max(abs(lhs), abs(rhs))
            )
            if absolute_tolerance
            + config["relative_tolerance"] * max(abs(lhs), abs(rhs))
            > 0.0
            else math.inf
            for error, lhs, rhs in zip(absolute, expected, actual)
        ]
        records.append(
            {
                "run_id": run_id,
                "tier": tier,
                "study": config["study"],
                "case": config["case"],
                "problem_id": config.get("problem_id", config["case"]),
                "surrogate_model": config["surrogate_model"],
                "repetition": repetition,
                "axis": config["axis"],
                "axis_value": config["axis_value"],
                "mesh_elements": config["mesh"],
                "chemical_elements": config["chemical_elements"],
                "relative_tolerance": config["relative_tolerance"],
                "output": output,
                "samples": len(expected),
                "max_absolute_error": max(absolute, default=0.0),
                "rmse": math.sqrt(sum(value * value for value in absolute) / len(absolute)),
                "p95_absolute_error": percentile(absolute, 0.95),
                "max_relative_error": max(relative, default=0.0),
                "p95_relative_error": percentile(relative, 0.95),
                "relative_scale_floor": scale_floor,
                "absolute_tolerance": absolute_tolerance,
                "absolute_tolerance_source": absolute_tolerance_source,
                "max_normalized_error": max(normalized, default=0.0),
                "p95_normalized_error": percentile(normalized, 0.95),
            }
        )
    return records


def calibrate_absolute_tolerances(
    case: str,
    warm_path: Path,
    cold_path: Path,
    overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    """Calibrate near-zero output tolerances without observing an adaptive result."""
    warm = read_samples(warm_path)
    cold = read_samples(cold_path)
    if len(warm) != len(cold):
        raise ValueError("Warm and cold exact calibration sample counts differ")
    validate_sample_invariants(case, warm)
    validate_sample_invariants(case, cold)
    tolerances = {}
    for output in CASE_OUTPUTS[case]:
        scale = max(
            max((abs(row[output]) for row in warm), default=0.0),
            max((abs(row[output]) for row in cold), default=0.0),
            1.0,
        )
        reproducibility = max(
            (abs(lhs[output] - rhs[output]) for lhs, rhs in zip(warm, cold)), default=0.0
        )
        tolerances[output] = max(
            10.0 * reproducibility, 100.0 * sys.float_info.epsilon * scale
        )
    for output, value in (overrides or {}).items():
        if output not in CASE_OUTPUTS[case]:
            raise ValueError(f"Absolute tolerance override names unknown output '{output}'")
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"Absolute tolerance override for {output} must be nonnegative")
        tolerances[output] = value
    return tolerances


def validate_nonoverlapping_trajectory(config: dict[str, Any]) -> None:
    """Reject population/query grids that contain identical composition coordinates."""
    if config.get("case") != "binary_comparison":
        return
    span = config["composition_max"] - config["composition_min"]
    if span <= 0.0:
        raise ValueError(f"{config['problem_id']} has a nonpositive composition span")
    displacement_in_cells = config["temporal_displacement"] * config["mesh"] / span
    if math.isclose(
        displacement_in_cells,
        round(displacement_in_cells),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"{config['problem_id']} population and query grids overlap exactly "
            f"({displacement_in_cells:g} mesh cells)"
        )


def expand_study(name: str, study: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "capability_comparison":
        configs = []
        for problem in study["problems"]:
            composition_min = float(problem["composition_min"])
            composition_max = float(problem["composition_max"])
            displacement = math.sqrt(2.0) * 1e-3 * (composition_max - composition_min)
            for mesh in study["meshes"]:
                for tolerance in study["tolerances"]:
                    for model in study["surrogate_models"]:
                        config = {
                            "study": name,
                            "case": "binary_comparison",
                            "problem_id": f"{problem['id']}-n{int(mesh)}",
                            "composition_min": composition_min,
                            "composition_max": composition_max,
                            "temporal_displacement": displacement,
                            "axis": "relative_tolerance",
                            "axis_value": float(tolerance),
                            "mesh": int(mesh),
                            "chemical_elements": 2,
                            "relative_tolerance": float(tolerance),
                            "neighbors": int(study.get("neighbors", 0)),
                            "cache_capacity": int(study.get("cache_capacity", 10000)),
                            "audit_interval": int(study.get("audit_interval", 100)),
                            "warm_start": "previous_solve",
                            "surrogate_model": str(model),
                            "threads": 1,
                            "ranks": 1,
                            "exact_only": False,
                            "absolute_tolerance_overrides": {
                                str(key): float(value)
                                for key, value in study.get(
                                    "absolute_tolerance_overrides", {}
                                ).items()
                            },
                        }
                        validate_nonoverlapping_trajectory(config)
                        configs.append(config)
        return configs

    cases = study["case"] if isinstance(study["case"], list) else [study["case"]]
    models = study.get("surrogate_models", [study.get("surrogate_model", "local_idw")])
    configs = []
    for case in cases:
        for value in study["values"]:
            selected_models = [value] if study["axis"] == "surrogate_model" else models
            for model in selected_models:
                mesh = study.get("mesh", 200)
                if isinstance(mesh, dict):
                    mesh = mesh[case]
                config = {
                    "study": name,
                    "case": case,
                    "problem_id": case,
                    "axis": study["axis"],
                    "axis_value": value,
                    "mesh": int(mesh),
                    "chemical_elements": (
                        17
                        if case.startswith("multielement_")
                        or case == "fluoride_dimension_trace"
                        else 2
                    ),
                    "relative_tolerance": float(study.get("relative_tolerance", 1e-4)),
                    "neighbors": int(study.get("neighbors", 0)),
                    "cache_capacity": 10000,
                    "audit_interval": int(study.get("audit_interval", 100)),
                    "warm_start": str(study.get("warm_start", "previous_solve")),
                    "surrogate_model": str(model),
                    "threads": 1,
                    "ranks": 1,
                    "exact_only": bool(study.get("exact_only", False)),
                }
                configured_elements = study.get("chemical_elements")
                if isinstance(configured_elements, dict) and case in configured_elements:
                    config["chemical_elements"] = int(configured_elements[case])
                axis = study["axis"]
                if axis == "relative_tolerance":
                    config["relative_tolerance"] = float(value)
                elif axis == "mesh":
                    config["mesh"] = int(value)
                elif axis == "chemical_elements":
                    config["chemical_elements"] = int(value)
                elif axis == "neighbors":
                    config["neighbors"] = 0 if value == "auto" else int(value)
                elif axis == "cache_capacity":
                    config["cache_capacity"] = int(value)
                elif axis == "audit_interval":
                    config["audit_interval"] = int(value)
                elif axis == "warm_start":
                    config["warm_start"] = str(value)
                elif axis == "surrogate_model":
                    config["surrogate_model"] = str(value)
                elif axis == "parallel":
                    config["threads"] = int(value["threads"])
                    config["ranks"] = int(value["ranks"])
                    config["axis_value"] = f"t{config['threads']}_r{config['ranks']}"
                elif axis == "output_set":
                    config["axis_value"] = case
                else:
                    raise ValueError(f"Unsupported study axis '{axis}'")
                configs.append(config)
    return configs


def command_for(
    executable: Path,
    mpiexec: str,
    exec_prefix: str | None,
    config: dict[str, Any],
    mode: str,
    file_base: Path,
) -> list[str]:
    command = [
        str(executable),
        "-i",
        str(CASE_FILES[config["case"]]),
        f"Mesh/gen/nx={config['mesh']}",
        f"ChemicalComposition/thermo/acceleration={mode}",
        f"ChemicalComposition/thermo/surrogate_model={config['surrogate_model']}",
        f"ChemicalComposition/thermo/warm_start={config['warm_start']}",
        f"ChemicalComposition/thermo/surrogate_relative_tolerance={config['relative_tolerance']}",
        f"ChemicalComposition/thermo/surrogate_neighbors={config['neighbors']}",
        f"ChemicalComposition/thermo/cache_max_entries={config['cache_capacity']}",
        f"ChemicalComposition/thermo/surrogate_audit_interval={config['audit_interval']}",
        f"Outputs/file_base={file_base}",
        f"--n-threads={config['threads']}",
    ]
    if config["case"].startswith("multielement_") or config["case"] == "fluoride_dimension_trace":
        command.append(
            f"ChemicalComposition/thermo/elements={ELEMENT_SETS[config['chemical_elements']]}"
        )
    if config["case"] == "binary_comparison":
        lower = config["composition_min"]
        span = config["composition_max"] - lower
        displacement = config["temporal_displacement"]
        mo_initial = f"{lower:.17g}+{span:.17g}*x"
        mo_query = f"{mo_initial}+{displacement:.17g}*t"
        ru_initial = f"1-({mo_initial})"
        ru_query = f"1-({mo_query})"
        command.extend(
            [
                f"ICs/mo/function={mo_initial}",
                f"ICs/ru/function={ru_initial}",
                f"AuxKernels/mo/function={mo_query}",
                f"AuxKernels/ru/function={ru_query}",
            ]
        )
    if config.get("surrogate_absolute_tolerances"):
        values = " ".join(
            f"{output}:{value:.17g}"
            for output, value in sorted(
                config["surrogate_absolute_tolerances"].items()
            )
        )
        command.append(
            f"ChemicalComposition/thermo/surrogate_absolute_tolerances={values}"
        )
    if exec_prefix:
        command = [exec_prefix] + command
    if config["ranks"] > 1 or config["study"] == "parallel":
        command = [mpiexec, "-n", str(config["ranks"])] + command
    return command


def run_process(command: list[str], log_path: Path) -> tuple[float, float | None, str]:
    peak_rss = None
    try:
        import psutil  # type: ignore
    except ImportError:
        psutil = None

    start = time.perf_counter()
    environment = os.environ.copy()
    if platform.system() == "Darwin":
        environment.setdefault("FI_PROVIDER", "tcp")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
        if psutil:
            monitored = psutil.Process(process.pid)
            peak_rss = 0
            while process.poll() is None:
                try:
                    processes = [monitored] + monitored.children(recursive=True)
                    peak_rss = max(peak_rss, sum(item.memory_info().rss for item in processes))
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    peak_rss = None
                    break
                time.sleep(0.01)
        return_code = process.wait()
    wall_time = time.perf_counter() - start
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if return_code:
        tail = "\n".join(text.splitlines()[-40:])
        raise RuntimeError(f"Benchmark command failed ({return_code}): {' '.join(command)}\n{tail}")
    return wall_time, peak_rss, text


def latest_sample(file_base: Path) -> Path:
    candidates = sorted(file_base.parent.glob(f"{file_base.name}_samples_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No ElementValueSampler CSV was produced for {file_base}")
    return candidates[-1]


def execute_once(
    executable: Path,
    mpiexec: str,
    exec_prefix: str | None,
    tier: str,
    config: dict[str, Any],
    mode: str,
    repetition: int,
    output: Path,
    commands: list[list[str]],
    prime: bool = False,
) -> dict[str, Any]:
    identity = (
        f"{config['study']}-{config.get('problem_id', config['case'])}-"
        f"{mode}-{config['surrogate_model']}-"
        f"{slug(config['axis_value'])}-r{repetition}"
    )
    if prime:
        identity += "-prime"
    file_base = output / "raw" / identity
    log_path = output / "logs" / f"{identity}.log"
    command = command_for(executable, mpiexec, exec_prefix, config, mode, file_base)
    commands.append(command)
    wall_time, peak_rss, text = run_process(command, log_path)
    stages = parse_telemetry(text)
    sample = latest_sample(file_base)
    return {
        "identity": identity,
        "wall_time": wall_time,
        "peak_rss": peak_rss,
        "stages": stages,
        "sample": sample,
        "log": log_path,
    }


def exact_key(config: dict[str, Any]) -> tuple[Any, ...]:
    return (
        config["study"],
        config["case"],
        config.get("problem_id", config["case"]),
        config.get("composition_min"),
        config.get("composition_max"),
        config.get("temporal_displacement"),
        config["mesh"],
        config["chemical_elements"],
        config["warm_start"],
        config["threads"],
        config["ranks"],
    )


def stage_rows(
    run_id: str,
    tier: str,
    config: dict[str, Any],
    mode: str,
    repetition: int,
    result: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = []
    last = len(result["stages"]) - 1
    for index, telemetry in enumerate(result["stages"]):
        stage = "initial" if index == 0 else "query" if index == last else "warmup"
        row = {
            "run_id": run_id,
            "tier": tier,
            "study": config["study"],
            "case": config["case"],
            "problem_id": config.get("problem_id", config["case"]),
            "composition_min": config.get("composition_min", ""),
            "composition_max": config.get("composition_max", ""),
            "temporal_displacement": config.get("temporal_displacement", ""),
            "mode": mode,
            "surrogate_model": config["surrogate_model"],
            "repetition": repetition,
            "stage_index": index,
            "stage": stage,
            "axis": config["axis"],
            "axis_value": config["axis_value"],
            "mesh_elements": config["mesh"],
            "chemical_elements": config["chemical_elements"],
            "relative_tolerance": config["relative_tolerance"],
            "neighbors": config["neighbors"],
            "cache_capacity": config["cache_capacity"],
            "audit_interval": config["audit_interval"],
            "warm_start": config["warm_start"],
            "threads": config["threads"],
            "ranks": config["ranks"],
            "wall_time": result["wall_time"],
            "peak_rss_bytes": result["peak_rss"] if result["peak_rss"] is not None else "",
            "sample_file": str(result["sample"]),
            "log_file": str(result["log"]),
        }
        row.update(telemetry)
        if baseline and index == last:
            base_query = baseline["stages"][-1]
            row["baseline_wall_time"] = baseline["wall_time"]
            row["baseline_worker_solve_time"] = base_query["worker_solve_time"]
            row["baseline_exact_solves"] = base_query["exact_solves"]
            row["wall_speedup"] = baseline["wall_time"] / result["wall_time"]
            row["worker_speedup"] = (
                base_query["worker_solve_time"] / telemetry["worker_solve_time"]
                if telemetry["worker_solve_time"]
                else math.inf
            )
            row["exact_call_reduction"] = (
                1.0 - telemetry["exact_solves"] / base_query["exact_solves"]
                if base_query["exact_solves"]
                else 0.0
            )
            # Accuracy is not available until sampled output has been compared.
            # report_results() is the sole authority for capability verdicts.
            row["meets_capability_gate"] = ""
        rows.append(row)
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def aggregate_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_rows = [row for row in rows if row["stage"] == "query"]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    keys = [
        "tier",
        "study",
        "case",
        "problem_id",
        "composition_min",
        "composition_max",
        "temporal_displacement",
        "mode",
        "axis",
        "axis_value",
        "mesh_elements",
        "chemical_elements",
        "relative_tolerance",
        "neighbors",
        "cache_capacity",
        "audit_interval",
        "warm_start",
        "threads",
        "ranks",
        "surrogate_model",
    ]
    for row in query_rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    numeric = list(dict.fromkeys([
        "wall_time",
        "peak_rss_bytes",
        *INT_FIELDS,
        *REJECTION_FIELDS,
        *TIME_FIELDS,
        "baseline_wall_time",
        "baseline_worker_solve_time",
        "baseline_exact_solves",
        "wall_speedup",
        "worker_speedup",
        "exact_call_reduction",
    ]))
    summary = []
    for group_key, group in groups.items():
        record = dict(zip(keys, group_key))
        record["repetitions"] = len(group)
        for field in numeric:
            values = []
            for row in group:
                value = row.get(field, "")
                if value not in ("", None):
                    values.append(float(value))
            record[f"{field}_median"] = median(values)
            record[f"{field}_iqr"] = iqr(values)
        record["meets_capability_gate"] = ""
        summary.append(record)
    return summary


def checkpoint_results(
    output: Path,
    rows: list[dict[str, Any]],
    accuracy: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    """Atomically publish completed repetitions so they can be plotted during a long run."""
    write_csv(output / "runs.csv", RUN_FIELDS, rows)
    write_csv(output / "accuracy.csv", ACCURACY_FIELDS, accuracy)
    write_csv(output / "failures.csv", FAILURE_FIELDS, failures)
    summary = aggregate_runs(rows)
    summary_fields = list(summary[0]) if summary else ["tier", "study", "case", "mode"]
    write_csv(output / "summary.csv", summary_fields, summary)


def metadata(executable: Path, tier: str, commands: list[list[str]]) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    packages = {}
    for package in ("matplotlib", "psutil"):
        try:
            module = __import__(package)
            packages[package] = getattr(module, "__version__", "unknown")
        except ImportError:
            packages[package] = None
    return {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tier": tier,
        "git_revision": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "executable": str(executable.resolve()),
        "python": sys.version,
        "conda_environment": os.environ.get("CONDA_DEFAULT_ENV"),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "packages": packages,
        "commands": commands,
    }


def run_suite(args: argparse.Namespace) -> Path:
    executable = Path(args.exe).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"MOOSE executable not found: {executable}")
    manifest = load_manifest(args.tier)
    available = manifest["studies"]
    requested = list(available) if args.study == "all" else [args.study]
    missing = [name for name in requested if name not in available]
    if missing:
        raise ValueError(f"Unknown {args.tier} study: {', '.join(missing)}")
    selected_cases = {
        config["case"]
        for study_name in requested
        for config in expand_study(study_name, available[study_name])
    }
    validate_case_databases(selected_cases)

    if args.output:
        output = Path(args.output).resolve()
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        output = ROOT / "results" / timestamp
    (output / "raw").mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(parents=True, exist_ok=True)
    (output / "figures").mkdir(parents=True, exist_ok=True)

    repetitions = args.repetitions or int(manifest["repetitions"])
    do_prime = bool(manifest.get("prime", False)) and not args.no_prime
    run_id = output.name
    commands: list[list[str]] = []
    rows: list[dict[str, Any]] = []
    accuracy: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    exact_results: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    absolute_tolerances: dict[tuple[Any, ...], dict[str, float]] = {}

    for study_name in requested:
        configs = expand_study(study_name, available[study_name])
        for config in configs:
            try:
                key = exact_key(config)
                if key not in exact_results:
                    if do_prime:
                        execute_once(
                            executable,
                            args.mpiexec,
                            args.exec_prefix,
                            args.tier,
                            config,
                            "exact",
                            -1,
                            output,
                            commands,
                            prime=True,
                        )
                    exact_results[key] = []
                    for repetition in range(repetitions):
                        result = execute_once(
                            executable,
                            args.mpiexec,
                            args.exec_prefix,
                            args.tier,
                            config,
                            "exact",
                            repetition,
                            output,
                            commands,
                        )
                        exact_results[key].append(result)
                        rows.extend(
                            stage_rows(run_id, args.tier, config, "exact", repetition, result, None)
                        )
                        checkpoint_results(output, rows, accuracy, failures)
                if config["study"] == "capability_comparison" and key not in absolute_tolerances:
                    cold_config = dict(config)
                    cold_config["warm_start"] = "none"
                    # Exact mode does not use the surrogate, but MOOSE still validates this enum.
                    cold_config["surrogate_model"] = "local_idw"
                    cold = execute_once(
                        executable,
                        args.mpiexec,
                        args.exec_prefix,
                        args.tier,
                        cold_config,
                        "exact",
                        -2,
                        output,
                        commands,
                        prime=True,
                    )
                    absolute_tolerances[key] = calibrate_absolute_tolerances(
                        config["case"],
                        exact_results[key][0]["sample"],
                        cold["sample"],
                        config.get("absolute_tolerance_overrides"),
                    )
                if config["study"] == "capability_comparison":
                    config["surrogate_absolute_tolerances"] = absolute_tolerances[key]
                if config["exact_only"]:
                    continue
                if do_prime:
                    execute_once(
                        executable,
                        args.mpiexec,
                        args.exec_prefix,
                        args.tier,
                        config,
                        "adaptive",
                        -1,
                        output,
                        commands,
                        prime=True,
                    )
                for repetition in range(repetitions):
                    baseline = exact_results[key][repetition]
                    result = execute_once(
                        executable,
                        args.mpiexec,
                        args.exec_prefix,
                        args.tier,
                        config,
                        "adaptive",
                        repetition,
                        output,
                        commands,
                    )
                    rows.extend(
                        stage_rows(
                            run_id, args.tier, config, "adaptive", repetition, result, baseline
                        )
                    )
                    accuracy.extend(
                        compare_samples(
                            run_id,
                            args.tier,
                            config,
                            repetition,
                            baseline["sample"],
                            result["sample"],
                            absolute_tolerances.get(key),
                            (
                                "manifest_override_and_exact_reproducibility"
                                if config.get("absolute_tolerance_overrides")
                                else "exact_warm_cold_reproducibility"
                            ),
                        )
                    )
                    checkpoint_results(output, rows, accuracy, failures)
            except RuntimeError as error:
                if args.fail_fast:
                    raise
                failures.append(
                    {
                        "tier": args.tier,
                        "study": config["study"],
                        "case": config["case"],
                        "problem_id": config.get("problem_id", config["case"]),
                        "surrogate_model": config["surrogate_model"],
                        "axis": config["axis"],
                        "axis_value": config["axis_value"],
                        "mesh_elements": config["mesh"],
                        "chemical_elements": config["chemical_elements"],
                        "threads": config["threads"],
                        "ranks": config["ranks"],
                        "error": str(error),
                    }
                )
                checkpoint_results(output, rows, accuracy, failures)

    checkpoint_results(output, rows, accuracy, failures)
    metadata_record = metadata(executable, args.tier, commands)
    metadata_record["absolute_tolerances"] = {
        "|".join(str(value) for value in key): values
        for key, values in absolute_tolerances.items()
    }
    with (output / "metadata.json").open("w", encoding="utf-8") as stream:
        json.dump(metadata_record, stream, indent=2)
        stream.write("\n")
    if not rows:
        raise RuntimeError(
            f"No benchmark configuration completed successfully; see {output / 'failures.csv'}"
        )
    report_results(output)
    if not args.skip_plots:
        plot_results(output)
    return output


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save_figure(figure: Any, directory: Path, name: str) -> None:
    figure.tight_layout()
    for extension in ("pdf", "svg", "png"):
        figure.savefig(
            directory / f"{name}.{extension}",
            dpi=300,
            bbox_inches="tight",
            pad_inches=0.05,
            transparent=True,
        )


def method_label(identifier: str) -> str:
    return METHOD_LABELS.get(identifier, identifier.replace("_", " ").title())


def place_legend_outside(axis: Any, **kwargs: Any) -> Any:
    return axis.legend(
        bbox_to_anchor=(1.02, 1.0),
        loc="upper left",
        borderaxespad=0.0,
        **kwargs,
    )


def numeric_axis(row: dict[str, str]) -> float:
    value = row["axis_value"]
    if row["axis"] == "parallel":
        return float(row["threads"]) if int(row["ranks"]) == 1 else float(row["ranks"])
    return float(value)


def finite_float(row: dict[str, str], field: str, default: float = math.nan) -> float:
    try:
        value = float(row.get(field, ""))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def comparison_key(row: dict[str, str]) -> tuple[Any, ...]:
    return (
        row.get("problem_id", row["case"]),
        int(float(row["mesh_elements"])),
        float(row["relative_tolerance"]),
    )


def comparison_accuracy(accuracy: list[dict[str, str]]) -> dict[tuple[Any, ...], float]:
    errors: dict[tuple[Any, ...], float] = {}
    for row in accuracy:
        if row["study"] not in ("capability_comparison", "algorithm_comparison"):
            continue
        key = (
            row.get("problem_id", row["case"]),
            int(float(row.get("mesh_elements", 0))),
            float(row.get("relative_tolerance", row["axis_value"])),
            row["surrogate_model"],
        )
        normalized = finite_float(row, "max_normalized_error")
        if not math.isfinite(normalized):
            tolerance = float(row.get("relative_tolerance", row["axis_value"]))
            normalized = finite_float(row, "max_relative_error") / tolerance
        errors[key] = max(errors.get(key, 0.0), normalized)
    return errors


def comparison_valid(
    row: dict[str, str], errors: dict[tuple[Any, ...], float]
) -> tuple[bool, float]:
    key = (*comparison_key(row), row["surrogate_model"])
    normalized = errors.get(key, math.inf)
    valid = (
        finite_float(row, "audit_failures_median", 0.0) == 0.0
        and finite_float(row, "state_restore_failures_median", 0.0) == 0.0
        and normalized <= 1.0
    )
    return valid, normalized


COMPARISON_FIELDS = [
    "tier",
    "study",
    "problem_id",
    "case",
    "algorithm",
    "method_label",
    "relative_tolerance",
    "mesh_elements",
    "composition_min",
    "composition_max",
    "temporal_displacement",
    "repetitions",
    "status",
    "failure_reasons",
    "accurate",
    "wall_time",
    "wall_speedup",
    "worker_solve_time",
    "worker_speedup",
    "exact_solves",
    "exact_call_reduction",
    "states",
    "exact_solves_per_state",
    "reuse_utilization",
    "approximate_utilization",
    "audit_utilization",
    "fallback_utilization",
    "max_normalized_error",
    "max_absolute_error",
    "rmse",
    "p95_absolute_error",
    "worst_output",
    "absolute_tolerances",
    "peak_rss_bytes",
    "audit_failures",
    "state_restore_failures",
]


def capability_status(
    normalized_error: float,
    audit_failures: float,
    state_restore_failures: float,
    exact_call_reduction: float,
    wall_speedup: float,
) -> tuple[str, list[str]]:
    reasons = []
    if (
        not math.isfinite(normalized_error)
        or normalized_error > 1.0
        or audit_failures != 0.0
        or state_restore_failures != 0.0
    ):
        reasons.append("accuracy or invariant requirement failed")
    if not math.isfinite(exact_call_reduction) or exact_call_reduction < 0.5:
        reasons.append("exact GEM call reduction is below 50%")
    if not math.isfinite(wall_speedup) or wall_speedup < 2.0:
        reasons.append("total wall-time speedup is below 2x")
    if not reasons:
        return "PASS", []
    if "accuracy or invariant requirement failed" in reasons:
        return "FAIL_ACCURACY", reasons
    if "exact GEM call reduction is below 50%" in reasons:
        return "FAIL_EXACT_REDUCTION", reasons
    return "FAIL_WALL_SPEEDUP", reasons


def utilization_counts(row: dict[str, str]) -> tuple[float, float, float, float, float]:
    states = max(finite_float(row, "states_median", 0.0), 0.0)
    reuse = max(finite_float(row, "exact_reuse_hits_median", 0.0), 0.0)
    approximate = max(finite_float(row, "surrogate_hits_median", 0.0), 0.0)
    audits = max(finite_float(row, "audits_median", 0.0), 0.0)
    fallback = max(states - reuse - approximate - audits, 0.0)
    if states and not math.isclose(
        reuse + approximate + audits + fallback, states, rel_tol=1e-10, abs_tol=1e-8
    ):
        raise ValueError("Query-state utilization counters do not form a partition")
    return states, reuse, approximate, audits, fallback


def report_results(directory: Path) -> None:
    """Create the correctness-gated tables used by every capability figure."""
    summary = load_csv(directory / "summary.csv")
    accuracy = load_csv(directory / "accuracy.csv")
    failures = load_csv(directory / "failures.csv")
    selected = [
        row
        for row in summary
        if row["study"] == "capability_comparison" and row["mode"] == "adaptive"
    ]
    accuracy_groups: dict[tuple[Any, ...], list[dict[str, str]]] = {}
    for row in accuracy:
        if row["study"] != "capability_comparison":
            continue
        key = (
            row.get("problem_id", row["case"]),
            int(float(row["mesh_elements"])),
            float(row["relative_tolerance"]),
            row["surrogate_model"],
        )
        accuracy_groups.setdefault(key, []).append(row)

    comparison: list[dict[str, Any]] = []
    exact_written = set()
    exact_rows = {
        (row.get("problem_id", row["case"]), int(float(row["mesh_elements"]))): row
        for row in summary
        if row["study"] == "capability_comparison" and row["mode"] == "exact"
    }
    for row in selected:
        problem_key = comparison_key(row)
        exact_key_value = problem_key[:2]
        if problem_key not in exact_written:
            exact = exact_rows.get(exact_key_value)
            baseline_wall = finite_float(row, "baseline_wall_time_median")
            baseline_worker = finite_float(row, "baseline_worker_solve_time_median")
            baseline_solves = finite_float(row, "baseline_exact_solves_median")
            states = max(finite_float(row, "states_median", 0.0), 0.0)
            comparison.append(
                {
                    "tier": row["tier"],
                    "study": row["study"],
                    "problem_id": row.get("problem_id", row["case"]),
                    "case": row["case"],
                    "algorithm": "exact_gem",
                    "method_label": method_label("exact_gem"),
                    "relative_tolerance": row["relative_tolerance"],
                    "mesh_elements": row["mesh_elements"],
                    "composition_min": row.get("composition_min", ""),
                    "composition_max": row.get("composition_max", ""),
                    "temporal_displacement": row.get("temporal_displacement", ""),
                    "repetitions": row["repetitions"],
                    "status": "REFERENCE",
                    "failure_reasons": "",
                    "accurate": 1,
                    "wall_time": baseline_wall,
                    "wall_speedup": 1.0,
                    "worker_solve_time": baseline_worker,
                    "worker_speedup": 1.0,
                    "exact_solves": baseline_solves,
                    "exact_call_reduction": 0.0,
                    "states": states,
                    "exact_solves_per_state": baseline_solves / states if states else math.nan,
                    "reuse_utilization": 0.0,
                    "approximate_utilization": 0.0,
                    "audit_utilization": 0.0,
                    "fallback_utilization": 1.0,
                    "max_normalized_error": 0.0,
                    "max_absolute_error": 0.0,
                    "rmse": 0.0,
                    "p95_absolute_error": 0.0,
                    "worst_output": "",
                    "absolute_tolerances": "",
                    "peak_rss_bytes": (
                        finite_float(exact, "peak_rss_bytes_median") if exact else math.nan
                    ),
                    "audit_failures": 0,
                    "state_restore_failures": 0,
                }
            )
            exact_written.add(problem_key)

        error_rows = accuracy_groups.get((*problem_key, row["surrogate_model"]), [])
        worst = max(
            error_rows,
            key=lambda item: finite_float(item, "max_normalized_error", math.inf),
            default=None,
        )
        normalized = (
            finite_float(worst, "max_normalized_error", math.inf) if worst else math.inf
        )
        audit_failures = finite_float(row, "audit_failures_median", 0.0)
        restore_failures = finite_float(row, "state_restore_failures_median", 0.0)
        reduction = finite_float(row, "exact_call_reduction_median", 0.0)
        wall_speedup = finite_float(row, "wall_speedup_median", 0.0)
        status, reasons = capability_status(
            normalized, audit_failures, restore_failures, reduction, wall_speedup
        )
        states, reuse, approximate, audits, fallback = utilization_counts(row)
        tolerances = {
            item["output"]: finite_float(item, "absolute_tolerance")
            for item in error_rows
        }
        comparison.append(
            {
                "tier": row["tier"],
                "study": row["study"],
                "problem_id": row.get("problem_id", row["case"]),
                "case": row["case"],
                "algorithm": row["surrogate_model"],
                "method_label": method_label(row["surrogate_model"]),
                "relative_tolerance": row["relative_tolerance"],
                "mesh_elements": row["mesh_elements"],
                "composition_min": row.get("composition_min", ""),
                "composition_max": row.get("composition_max", ""),
                "temporal_displacement": row.get("temporal_displacement", ""),
                "repetitions": row["repetitions"],
                "status": status,
                "failure_reasons": "; ".join(reasons),
                "accurate": int(
                    normalized <= 1.0
                    and audit_failures == 0
                    and restore_failures == 0
                ),
                "wall_time": finite_float(row, "wall_time_median"),
                "wall_speedup": wall_speedup,
                "worker_solve_time": finite_float(row, "worker_solve_time_median"),
                "worker_speedup": finite_float(row, "worker_speedup_median"),
                "exact_solves": finite_float(row, "exact_solves_median"),
                "exact_call_reduction": reduction,
                "states": states,
                "exact_solves_per_state": (
                    finite_float(row, "exact_solves_median") / states if states else math.nan
                ),
                "reuse_utilization": reuse / states if states else math.nan,
                "approximate_utilization": approximate / states if states else math.nan,
                "audit_utilization": audits / states if states else math.nan,
                "fallback_utilization": fallback / states if states else math.nan,
                "max_normalized_error": normalized,
                "max_absolute_error": max(
                    (finite_float(item, "max_absolute_error") for item in error_rows),
                    default=math.inf,
                ),
                "rmse": max(
                    (finite_float(item, "rmse") for item in error_rows), default=math.inf
                ),
                "p95_absolute_error": max(
                    (finite_float(item, "p95_absolute_error") for item in error_rows),
                    default=math.inf,
                ),
                "worst_output": worst["output"] if worst else "",
                "absolute_tolerances": json.dumps(tolerances, sort_keys=True),
                "peak_rss_bytes": finite_float(row, "peak_rss_bytes_median"),
                "audit_failures": audit_failures,
                "state_restore_failures": restore_failures,
            }
        )

    for failure in failures:
        if failure.get("study") != "capability_comparison":
            continue
        comparison.append(
            {
                "tier": failure.get("tier", ""),
                "study": failure["study"],
                "problem_id": failure.get("problem_id", failure["case"]),
                "case": failure["case"],
                "algorithm": failure.get("surrogate_model", "unknown"),
                "method_label": method_label(
                    failure.get("surrogate_model", "unknown")
                ),
                "relative_tolerance": failure.get("axis_value", ""),
                "mesh_elements": failure.get("mesh_elements", ""),
                "status": "RUN_FAILED",
                "failure_reasons": failure["error"],
                "accurate": 0,
            }
        )

    write_csv(directory / "comparison.csv", COMPARISON_FIELDS, comparison)
    adaptive = [row for row in comparison if row["algorithm"] != "exact_gem"]
    gate_fields = [
        "problem_id",
        "algorithm",
        "method_label",
        "relative_tolerance",
        "status",
        "failure_reasons",
        "wall_speedup",
        "exact_call_reduction",
        "max_normalized_error",
        "worst_output",
    ]
    write_csv(directory / "capability_gate.csv", gate_fields, adaptive)
    utilization_fields = [
        "problem_id",
        "algorithm",
        "method_label",
        "relative_tolerance",
        "states",
        "exact_solves_per_state",
        "reuse_utilization",
        "approximate_utilization",
        "audit_utilization",
        "fallback_utilization",
    ]
    write_csv(directory / "utilization.csv", utilization_fields, comparison)

    fluoride_cases = {
        "multielement_fluoride",
        "fluoride_dimension_trace",
        "lif_excess_f",
        "lif_low_temperature",
        "flibe_msfl",
    }
    qualification = []
    for row in summary:
        if row["case"] not in fluoride_cases or row["mode"] != "adaptive":
            continue
        unsupported = finite_float(row, "unsupported_model_rejections_median", 0.0)
        qualification.append(
            {
                "study": row["study"],
                "case": row["case"],
                "algorithm": row["surrogate_model"],
                "method_label": method_label(row["surrogate_model"]),
                "status": (
                    "UNSUPPORTED_EXACT_FALLBACK" if unsupported else "COVERAGE_RESULT"
                ),
                "unsupported_model_rejections": unsupported,
                "audit_failures": finite_float(row, "audit_failures_median", 0.0),
                "state_restore_failures": finite_float(
                    row, "state_restore_failures_median", 0.0
                ),
                "exact_call_reduction": finite_float(
                    row, "exact_call_reduction_median", 0.0
                ),
            }
        )
    qualification_fields = [
        "study",
        "case",
        "algorithm",
        "method_label",
        "status",
        "unsupported_model_rejections",
        "audit_failures",
        "state_restore_failures",
        "exact_call_reduction",
    ]
    write_csv(directory / "qualification.csv", qualification_fields, qualification)

    status_counts: dict[str, int] = {}
    for row in adaptive:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    report_lines = [
        "# Adaptive Thermochimica capability report",
        "",
        "Capability results use total application wall time and exhaustive sampled accuracy.",
        "Full GEM solves every state directly. Adaptive local interpolation uses nearby "
        "validated equilibria. Adaptive KKT sensitivity uses local equilibrium derivatives.",
        "Both adaptive methods fall back to Full GEM whenever their safeguards reject a "
        "prediction.",
        "Fluoride fallback studies are reported separately as qualification coverage.",
        "",
        "## Capability verdicts",
        "",
    ]
    if adaptive:
        report_lines.extend(
            f"- {status}: {count}" for status, count in sorted(status_counts.items())
        )
    else:
        report_lines.append("- No capability-comparison configurations have completed.")
    if failures:
        report_lines.extend(["", "## Run failures", "", f"- Recorded failures: {len(failures)}"])
    report_lines.extend(
        [
            "",
            "See `comparison.csv` for measurements, `capability_gate.csv` for verdicts, "
            "and `qualification.csv` for fail-closed fluoride coverage.",
            "",
        ]
    )
    (directory / "report.md").write_text("\n".join(report_lines), encoding="utf-8")


def profile_curve(ratios: list[float], problems: int) -> tuple[list[float], list[float]]:
    finite = sorted(value for value in ratios if math.isfinite(value))
    upper = max(finite, default=1.0)
    taus = sorted({1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0, upper})
    taus = [value for value in taus if value <= max(10.0, upper)]
    fractions = [sum(value <= tau for value in finite) / problems for tau in taus]
    return taus, fractions


def plot_results(directory: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(f"Plot generation requires matplotlib: {error}") from error
    plt.style.use(str(PLOT_STYLE))
    if shutil.which("latex") is None:
        plt.rcParams["text.usetex"] = False
        print(
            "warning: LaTeX was not found; using Matplotlib text rendering",
            file=sys.stderr,
        )

    report_results(directory)
    summary = load_csv(directory / "summary.csv")
    accuracy = load_csv(directory / "accuracy.csv")
    runs = load_csv(directory / "runs.csv")
    headline_figures = directory / "figures"
    headline_figures.mkdir(parents=True, exist_ok=True)
    figures = headline_figures / "diagnostics"
    figures.mkdir(parents=True, exist_ok=True)

    tolerance = [
        row
        for row in summary
        if row["axis"] == "relative_tolerance"
        and row["case"] == "binary_smooth"
        and row["mode"] == "adaptive"
    ]
    if tolerance:
        tolerance.sort(key=numeric_axis)
        figure, axes = plt.subplots(1, 2, figsize=(9, 3.8))
        x = [numeric_axis(row) for row in tolerance]
        axes[0].semilogx(x, [float(row["worker_speedup_median"]) for row in tolerance], "o-")
        axes[0].axhline(2.0, color="black", linestyle="--", linewidth=1)
        axes[0].set(xlabel="Relative tolerance", ylabel="Worker speedup")
        axes[1].semilogx(
            x, [100 * float(row["exact_call_reduction_median"]) for row in tolerance], "o-"
        )
        axes[1].axhline(50.0, color="black", linestyle="--", linewidth=1)
        axes[1].set(xlabel="Relative tolerance", ylabel="Exact-call reduction (%)")
        save_figure(figure, figures, "tolerance_speedup")
        plt.close(figure)

        errors: dict[float, float] = {}
        for row in accuracy:
            if row["axis"] == "relative_tolerance" and row["case"] == "binary_smooth":
                axis = float(row["axis_value"])
                errors[axis] = max(errors.get(axis, 0.0), float(row["max_relative_error"]))
        if errors:
            figure, axis = plt.subplots(figsize=(5, 3.8))
            values = sorted(errors)
            axis.loglog(values, [errors[value] for value in values], "o-", label="measured")
            axis.loglog(values, values, "k--", linewidth=1, label="requested")
            axis.set(xlabel="Relative tolerance", ylabel="Maximum scaled relative error")
            axis.legend()
            save_figure(figure, figures, "tolerance_error")
            plt.close(figure)

    mesh = [row for row in summary if row["axis"] == "mesh"]
    if mesh:
        figure, axes = plt.subplots(1, 2, figsize=(9, 3.8))
        for mode in ("exact", "adaptive"):
            selected = sorted((row for row in mesh if row["mode"] == mode), key=numeric_axis)
            if not selected:
                continue
            label = method_label(
                "exact_gem" if mode == "exact" else selected[0]["surrogate_model"]
            )
            axes[0].loglog(
                [numeric_axis(row) for row in selected],
                [float(row["wall_time_median"]) for row in selected],
                "o-",
                label=label,
            )
            axes[1].loglog(
                [numeric_axis(row) for row in selected],
                [float(row["worker_solve_time_median"]) for row in selected],
                "o-",
                label=label,
            )
        axes[0].set(xlabel="Mesh elements", ylabel="Application wall time (s)")
        axes[1].set(xlabel="Mesh elements", ylabel="Query worker time (s)")
        axes[0].legend()
        save_figure(figure, figures, "mesh_scaling")
        plt.close(figure)

    elements = [row for row in summary if row["axis"] == "chemical_elements"]
    if elements:
        figure, axes = plt.subplots(1, 3, figsize=(13, 3.8))
        for mode in ("exact", "adaptive"):
            selected = sorted((row for row in elements if row["mode"] == mode), key=numeric_axis)
            if not selected:
                continue
            label = method_label(
                "exact_gem" if mode == "exact" else selected[0]["surrogate_model"]
            )
            axes[0].plot(
                [numeric_axis(row) for row in selected],
                [float(row["worker_solve_time_median"]) for row in selected],
                "o-",
                label=label,
            )
            axes[2].plot(
                [numeric_axis(row) for row in selected],
                [float(row["peak_rss_bytes_median"]) / (1024 * 1024) for row in selected],
                "o-",
                label=label,
            )
        adaptive = sorted((row for row in elements if row["mode"] == "adaptive"), key=numeric_axis)
        axes[1].plot(
            [numeric_axis(row) for row in adaptive],
            [
                100 * float(row["surrogate_hits_median"])
                / max(float(row["surrogate_hits_median"]) + float(row["exact_solves_median"]), 1)
                for row in adaptive
            ],
            "o-",
        )
        axes[0].set(xlabel="Chemical elements", ylabel="Query worker time (s)")
        axes[0].legend()
        axes[1].set(xlabel="Chemical elements", ylabel="Surrogate hit rate (%)")
        axes[2].set(xlabel="Chemical elements", ylabel="Peak process-tree RSS (MiB)")
        save_figure(figure, figures, "element_scaling")
        plt.close(figure)

    parallel = [row for row in summary if row["axis"] == "parallel" and row["mode"] == "adaptive"]
    if parallel:
        figure, axes = plt.subplots(1, 3, figsize=(13, 3.8))
        for case in sorted({row["case"] for row in parallel}):
            for topology, field in (("threads", "threads"), ("ranks", "ranks")):
                selected = [
                    row
                    for row in parallel
                    if row["case"] == case
                    and ((topology == "threads" and int(row["ranks"]) == 1)
                         or (topology == "ranks" and int(row["threads"]) == 1))
                ]
                selected.sort(key=lambda row: int(row[field]))
                if not selected:
                    continue
                base = float(selected[0]["wall_time_median"])
                counts = [int(row[field]) for row in selected]
                speedups = [base / float(row["wall_time_median"]) for row in selected]
                label = f"{case}:{topology}"
                axes[0].plot(counts, speedups, "o-", label=label)
                axes[1].plot(counts, [speedup / count for speedup, count in zip(speedups, counts)], "o-", label=label)
                axes[2].plot(
                    counts,
                    [
                        100 * float(row["surrogate_hits_median"])
                        / max(float(row["surrogate_hits_median"]) + float(row["exact_solves_median"]), 1)
                        for row in selected
                    ],
                    "o-",
                    label=label,
                )
        axes[0].set(xlabel="Workers", ylabel="Wall-time speedup")
        axes[1].set(xlabel="Workers", ylabel="Parallel efficiency")
        axes[2].set(xlabel="Workers", ylabel="Surrogate hit rate (%)")
        axes[0].legend(fontsize="small")
        save_figure(figure, figures, "parallel_scaling")
        plt.close(figure)

    boundary = [row for row in summary if row["case"] == "binary_boundary" and row["mode"] == "adaptive"]
    if boundary:
        boundary.sort(key=numeric_axis)
        figure, axis = plt.subplots(figsize=(6, 4))
        x = [str(row["axis_value"]) for row in boundary]
        bottom = [0.0] * len(boundary)
        for field, label in (
            ("phase_rejections_median", "phase"),
            ("geometry_rejections_median", "geometry"),
            ("error_rejections_median", "error"),
            ("invariant_rejections_median", "invariant"),
        ):
            values = [float(row[field]) for row in boundary]
            axis.bar(x, values, bottom=bottom, label=label)
            bottom = [lhs + rhs for lhs, rhs in zip(bottom, values)]
        axis.set(xlabel="Relative tolerance", ylabel="Query rejections")
        axis.legend()
        save_figure(figure, figures, "boundary_rejections")
        plt.close(figure)

    cache = [row for row in summary if row["axis"] == "cache_capacity" and row["mode"] == "adaptive"]
    if cache:
        cache.sort(key=numeric_axis)
        figure, axes = plt.subplots(1, 3, figsize=(13, 3.8))
        x = [numeric_axis(row) for row in cache]
        axes[0].loglog(x, [float(row["cache_entries_median"]) for row in cache], "o-")
        axes[0].set(xlabel="Cache capacity", ylabel="Final cache entries")
        axes[1].semilogx(x, [float(row["cache_saturated_median"]) for row in cache], "o-")
        axes[1].set(xlabel="Cache capacity", ylabel="Cache saturated")
        axes[2].semilogx(x, [float(row["worker_speedup_median"]) for row in cache], "o-")
        axes[2].set(xlabel="Cache capacity", ylabel="Worker speedup")
        save_figure(figure, figures, "cache_scaling")
        plt.close(figure)


    models = [
        row for row in summary if row["axis"] == "surrogate_model" and row["mode"] == "adaptive"
    ]
    if models:
        figure, axes = plt.subplots(1, 3, figsize=(13, 3.8))
        labels = [
            f"{row['case']}\n{method_label(row['surrogate_model'])}"
            for row in models
        ]
        axes[0].bar(labels, [float(row["worker_speedup_median"]) for row in models])
        axes[1].bar(
            labels, [100 * float(row["exact_call_reduction_median"]) for row in models]
        )
        axes[2].bar(labels, [float(row["sensitivity_time_median"]) for row in models])
        axes[0].axhline(2.0, color="black", linestyle="--", linewidth=1)
        axes[1].axhline(50.0, color="black", linestyle="--", linewidth=1)
        axes[0].set(ylabel="Query worker speedup")
        axes[1].set(ylabel="Exact-call reduction (%)")
        axes[2].set(ylabel="Sensitivity construction time (s)")
        for axis in axes:
            axis.tick_params(axis="x", labelrotation=20)
        save_figure(figure, figures, "surrogate_model_comparison")
        plt.close(figure)

    comparison = [
        row
        for row in summary
        if row["study"] == "algorithm_comparison" and row["mode"] == "adaptive"
    ]
    if comparison:
        errors = comparison_accuracy(accuracy)
        algorithms = sorted({row["surrogate_model"] for row in comparison})
        problems: dict[tuple[Any, ...], dict[str, dict[str, str]]] = {}
        for row in comparison:
            problems.setdefault(comparison_key(row), {})[row["surrogate_model"]] = row

        figure, axes = plt.subplots(1, 2, figsize=(10, 4))
        for axis, adaptive_field, exact_field, title in (
            (axes[0], "worker_solve_time_median", "baseline_worker_solve_time_median", "Query worker"),
            (axes[1], "wall_time_median", "baseline_wall_time_median", "Application wall"),
        ):
            ratios: dict[str, list[float]] = {"exact": []}
            ratios.update({algorithm: [] for algorithm in algorithms})
            for entries in problems.values():
                representative = next(iter(entries.values()))
                costs = {"exact": finite_float(representative, exact_field)}
                for algorithm, row in entries.items():
                    valid, _ = comparison_valid(row, errors)
                    costs[algorithm] = finite_float(row, adaptive_field) if valid else math.inf
                best = min(value for value in costs.values() if math.isfinite(value) and value > 0.0)
                for algorithm in ratios:
                    cost = costs.get(algorithm, math.inf)
                    ratios[algorithm].append(cost / best if math.isfinite(cost) else math.inf)
            for algorithm, values in ratios.items():
                tau, fraction = profile_curve(values, len(problems))
                axis.step(tau, fraction, where="post", label=method_label(algorithm))
            axis.set_xscale("log")
            axis.set(
                xlabel=r"Performance ratio $\tau$",
                ylabel="Fraction of valid problems",
                title=f"{title}-time profile",
                ylim=(0.0, 1.03),
            )
            axis.axvline(2.0, color="black", linestyle="--", linewidth=0.8)
            axis.grid(alpha=0.25)
        axes[0].legend()
        save_figure(figure, figures, "algorithm_performance_profiles")
        plt.close(figure)

        budgets: dict[str, list[float]] = {"exact": []}
        budgets.update({algorithm: [] for algorithm in algorithms})
        for entries in problems.values():
            representative = next(iter(entries.values()))
            states = max(finite_float(representative, "states_median", 1.0), 1.0)
            budgets["exact"].append(
                finite_float(representative, "baseline_exact_solves_median") / states
            )
            for algorithm in algorithms:
                row = entries.get(algorithm)
                if row is None:
                    budgets[algorithm].append(math.inf)
                    continue
                valid, _ = comparison_valid(row, errors)
                value = finite_float(row, "exact_solves_median") / states
                budgets[algorithm].append(value if valid else math.inf)
        finite_budgets = sorted(
            {value for values in budgets.values() for value in values if math.isfinite(value)}
        )
        if finite_budgets:
            figure, axis = plt.subplots(figsize=(6, 4))
            beta = sorted({0.0, *finite_budgets, 1.0})
            for algorithm, values in budgets.items():
                fractions = [
                    sum(value <= limit for value in values if math.isfinite(value)) / len(problems)
                    for limit in beta
                ]
                axis.step(beta, fractions, where="post", label=method_label(algorithm))
            axis.set(
                xlabel="Exact GEM calls per query state",
                ylabel="Fraction of valid problems",
                title="Exact-call data profile",
                ylim=(0.0, 1.03),
            )
            axis.grid(alpha=0.25)
            axis.legend()
            save_figure(figure, figures, "algorithm_data_profile")
            plt.close(figure)

        figure, axes = plt.subplots(1, 2, figsize=(10, 4))
        for algorithm in algorithms:
            selected = [row for row in comparison if row["surrogate_model"] == algorithm]
            x = []
            time_values = []
            speedups = []
            valid_points = []
            for row in selected:
                valid, normalized = comparison_valid(row, errors)
                x.append(max(normalized, 1e-12))
                time_values.append(finite_float(row, "worker_solve_time_median"))
                speedups.append(finite_float(row, "worker_speedup_median"))
                valid_points.append(valid)
            for valid, marker in ((True, "o"), (False, "x")):
                indices = [index for index, value in enumerate(valid_points) if value == valid]
                if not indices:
                    continue
                label = algorithm if valid else f"{algorithm} invalid"
                axes[0].scatter(
                    [x[index] for index in indices],
                    [time_values[index] for index in indices],
                    marker=marker,
                    label=label,
                )
                axes[1].scatter(
                    [x[index] for index in indices],
                    [speedups[index] for index in indices],
                    marker=marker,
                    label=label,
                )
        for axis in axes:
            axis.set_xscale("log")
            axis.axvline(1.0, color="black", linestyle="--", linewidth=0.8)
            axis.grid(alpha=0.25)
        axes[0].set(
            xlabel="Maximum normalized error",
            ylabel="Query worker time (s)",
            yscale="log",
            title="Work-precision diagram",
        )
        axes[1].set(
            xlabel="Maximum normalized error",
            ylabel="Query worker speedup",
            title="Speedup-accuracy Pareto view",
        )
        axes[1].axhline(2.0, color="black", linestyle=":", linewidth=0.8)
        axes[0].legend(fontsize="small")
        save_figure(figure, figures, "algorithm_work_precision")
        plt.close(figure)

        cases = sorted({row["case"] for row in comparison})
        heatmap = []
        annotations = []
        for case in cases:
            heatmap_row = []
            annotation_row = []
            for algorithm in algorithms:
                selected = [
                    row
                    for row in comparison
                    if row["case"] == case and row["surrogate_model"] == algorithm
                ]
                valid_values = [
                    finite_float(row, "worker_speedup_median")
                    for row in selected
                    if comparison_valid(row, errors)[0]
                ]
                value = median(valid_values)
                heatmap_row.append(value if math.isfinite(value) else 0.0)
                annotation_row.append(f"{value:.2g}x" if math.isfinite(value) else "invalid")
            heatmap.append(heatmap_row)
            annotations.append(annotation_row)
        figure, axis = plt.subplots(figsize=(max(5, 1.8 * len(algorithms)), max(3.5, 0.55 * len(cases))))
        image = axis.imshow(heatmap, aspect="auto", cmap="viridis")
        axis.set_xticks(range(len(algorithms)), algorithms)
        axis.set_yticks(range(len(cases)), cases)
        axis.set(title="Median valid query-worker speedup")
        for row_index, row in enumerate(annotations):
            for column_index, text_value in enumerate(row):
                axis.text(column_index, row_index, text_value, ha="center", va="center", color="white")
        figure.colorbar(image, ax=axis, label="Speedup")
        save_figure(figure, figures, "algorithm_speedup_heatmap")
        plt.close(figure)

        stage_rows_selected = [
            row
            for row in runs
            if row["study"] == "algorithm_comparison"
            and int(row["repetition"]) == 0
            and row["case"] in ("binary_smooth", "binary_boundary")
        ]
        if stage_rows_selected:
            figure, axes = plt.subplots(1, 2, figsize=(10, 4))
            groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
            for row in stage_rows_selected:
                algorithm = "exact" if row["mode"] == "exact" else row["surrogate_model"]
                groups.setdefault((row["case"], algorithm, row["axis_value"]), []).append(row)
            for (case, algorithm, tolerance), group in groups.items():
                group.sort(key=lambda row: int(row["stage_index"]))
                stages = [row["stage"] for row in group]
                axes[0].plot(
                    stages,
                    [
                        finite_float(row, "exact_solves") / max(finite_float(row, "states"), 1.0)
                        for row in group
                    ],
                    "o-",
                    label=f"{case}:{algorithm}:{tolerance}",
                )
                axes[1].plot(
                    stages,
                    [finite_float(row, "cache_entries") for row in group],
                    "o-",
                    label=f"{case}:{algorithm}:{tolerance}",
                )
            axes[0].set(xlabel="Execution stage", ylabel="Exact calls per state")
            axes[1].set(xlabel="Execution stage", ylabel="Cache entries")
            axes[0].legend(fontsize="x-small")
            save_figure(figure, figures, "algorithm_stage_learning")
            plt.close(figure)

        boundary_runs = [
            row
            for row in runs
            if row["study"] == "algorithm_comparison"
            and row["case"] == "binary_boundary"
            and row["stage"] == "query"
            and int(row["repetition"]) == 0
        ]
        exact_boundary = next((row for row in boundary_runs if row["mode"] == "exact"), None)
        adaptive_boundary = [row for row in boundary_runs if row["mode"] == "adaptive"]
        if exact_boundary and adaptive_boundary:
            exact_path = Path(exact_boundary["sample_file"])
            if exact_path.is_file():
                exact_samples = read_samples(exact_path)
                coordinate = [row.get("x", row.get("id", 0.0)) for row in exact_samples]
                figure, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
                for output, label in (
                    ("bcc_fraction", "BCC"),
                    ("hcp_fraction", "HCP"),
                    ("fcc_fraction", "FCC"),
                    ("liquid_fraction", "liquid"),
                    ("sigma_fraction", "sigma"),
                ):
                    values = [row[output] for row in exact_samples]
                    if any(value > 1e-12 for value in values):
                        axes[0].plot(coordinate, values, label=f"Full GEM {label}")
                for row in adaptive_boundary:
                    sample_path = Path(row["sample_file"])
                    if not sample_path.is_file():
                        continue
                    samples = read_samples(sample_path)
                    maximum_error = [
                        max(
                            abs(expected[output] - actual[output])
                            for output in CASE_OUTPUTS["binary_boundary"]
                        )
                        for expected, actual in zip(exact_samples, samples)
                    ]
                    axes[1].semilogy(
                        coordinate,
                        [max(value, 1e-18) for value in maximum_error],
                        label=(
                            f"{row['surrogate_model']} "
                            f"(phase={row['phase_rejections']}, geometry={row['geometry_rejections']})"
                        ),
                    )
                axes[0].set(ylabel="Exact phase fraction")
                axes[1].set(xlabel="Trajectory coordinate", ylabel="Maximum absolute output error")
                axes[0].legend()
                axes[1].legend(fontsize="small")
                save_figure(figure, figures, "phase_boundary_trajectory")
                plt.close(figure)

    plot_capability_results(directory, headline_figures, plt)


def plot_capability_results(directory: Path, figures: Path, plt: Any) -> None:
    rows = load_csv(directory / "comparison.csv")
    if not rows:
        return
    tolerances = sorted({float(row["relative_tolerance"]) for row in rows})
    algorithms = ["exact_gem", "local_idw", "kkt_linear"]

    for tolerance in tolerances:
        selected = [row for row in rows if float(row["relative_tolerance"]) == tolerance]
        problems = sorted({row["problem_id"] for row in selected})
        entries = {
            (row["problem_id"], row["algorithm"]): row
            for row in selected
        }
        figure, axes = plt.subplots(1, 2, figsize=(10, 4))
        for axis, field, title in (
            (axes[0], "wall_time", "Total application wall time"),
            (axes[1], "worker_solve_time", "Thermochimica query-worker time"),
        ):
            ratios = {algorithm: [] for algorithm in algorithms}
            for problem in problems:
                costs = {}
                for algorithm in algorithms:
                    row = entries.get((problem, algorithm))
                    valid = row is not None and (
                        algorithm == "exact_gem" or int(row["accurate"]) == 1
                    )
                    costs[algorithm] = finite_float(row, field) if valid and row else math.inf
                finite_costs = [
                    value for value in costs.values() if math.isfinite(value) and value > 0.0
                ]
                best = min(finite_costs) if finite_costs else math.inf
                for algorithm, cost in costs.items():
                    ratios[algorithm].append(
                        cost / best
                        if math.isfinite(cost) and math.isfinite(best)
                        else math.inf
                    )
            for algorithm in algorithms:
                tau, fraction = profile_curve(ratios[algorithm], len(problems))
                axis.step(
                    tau,
                    fraction,
                    where="post",
                    label=method_label(algorithm),
                    color=METHOD_COLORS[algorithm],
                    linestyle=METHOD_LINESTYLES[algorithm],
                )
            axis.set_xscale("log")
            axis.set(
                xlabel=r"Performance ratio $\tau$",
                ylabel="Fraction of all problems",
                title=title,
                ylim=(0.0, 1.03),
            )
            axis.axvline(2.0, color="0.5", linestyle="--", linewidth=0.8)
            axis.grid(alpha=0.25)
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.08),
            ncol=3,
        )
        figure.suptitle(
            f"Safeguarded equilibrium methods at relative tolerance "
            rf"$10^{{{int(round(math.log10(tolerance)))}}}$"
        )
        save_figure(
            figure,
            figures,
            f"performance_profile_tolerance_{slug(tolerance)}",
        )
        plt.close(figure)

        figure, axis = plt.subplots(figsize=(6, 4))
        budgets = {algorithm: [] for algorithm in algorithms}
        for problem in problems:
            for algorithm in algorithms:
                row = entries.get((problem, algorithm))
                valid = row is not None and (
                    algorithm == "exact_gem" or int(row["accurate"]) == 1
                )
                budgets[algorithm].append(
                    finite_float(row, "exact_solves_per_state")
                    if valid and row
                    else math.inf
                )
        finite_budgets = sorted(
            {
                value
                for values in budgets.values()
                for value in values
                if math.isfinite(value)
            }
        )
        limits = sorted({0.0, *finite_budgets, 1.0})
        for algorithm, values in budgets.items():
            fractions = [
                sum(value <= limit for value in values if math.isfinite(value))
                / len(problems)
                for limit in limits
            ]
            axis.step(
                limits,
                fractions,
                where="post",
                label=method_label(algorithm),
                color=METHOD_COLORS[algorithm],
                linestyle=METHOD_LINESTYLES[algorithm],
            )
        axis.set(
            xlabel="Exact GEM calls per query state",
            ylabel="Fraction of all problems",
            title=f"Exact-call data profile, tolerance {tolerance:g}",
            ylim=(0.0, 1.03),
        )
        axis.grid(alpha=0.25)
        place_legend_outside(axis)
        save_figure(figure, figures, f"data_profile_tolerance_{slug(tolerance)}")
        plt.close(figure)

    adaptive = [row for row in rows if row["algorithm"] != "exact_gem"]
    if adaptive:
        figure, axis = plt.subplots(figsize=(7, 5))
        for algorithm in ("local_idw", "kkt_linear"):
            selected = [row for row in adaptive if row["algorithm"] == algorithm]
            for accurate, marker, suffix in ((True, "o", ""), (False, "x", " inaccurate")):
                points = [row for row in selected if bool(int(row["accurate"])) == accurate]
                if not points:
                    continue
                axis.scatter(
                    [max(finite_float(row, "max_normalized_error"), 1e-14) for row in points],
                    [finite_float(row, "wall_speedup") for row in points],
                    marker=marker,
                    color=METHOD_COLORS[algorithm],
                    label=f"{method_label(algorithm)}{suffix}",
                )
        axis.set_xscale("log")
        axis.axvline(1.0, color="black", linestyle="--", linewidth=0.8)
        axis.axhline(2.0, color="black", linestyle=":", linewidth=0.8)
        axis.set(
            xlabel="Maximum normalized error",
            ylabel="Total wall-time speedup",
            title="Work-precision capability comparison",
        )
        axis.grid(alpha=0.25)
        place_legend_outside(axis)
        save_figure(figure, figures, "work_precision")
        plt.close(figure)

        primary = min(tolerances, key=lambda value: abs(math.log10(value) + 4.0))
        utilization = [
            row for row in adaptive if float(row["relative_tolerance"]) == primary
        ]
        utilization.sort(key=lambda row: (row["problem_id"], row["algorithm"]))
        if utilization:
            labels = [
                f"{row['problem_id']}\n{method_label(row['algorithm'])}"
                for row in utilization
            ]
            figure, axis = plt.subplots(
                figsize=(max(8, 0.55 * len(utilization)), 5)
            )
            bottom = [0.0] * len(utilization)
            for field, label, color, hatch in (
                ("reuse_utilization", "Exact cache reuse", "#56B4E9", ""),
                ("approximate_utilization", "Accepted prediction", "#009E73", "//"),
                ("audit_utilization", "Audited Full GEM", "#CC79A7", "\\\\"),
                ("fallback_utilization", "Safeguarded Full GEM fallback", "#999999", ".."),
            ):
                values = [finite_float(row, field, 0.0) for row in utilization]
                axis.bar(
                    labels,
                    values,
                    bottom=bottom,
                    label=label,
                    color=color,
                    hatch=hatch,
                    edgecolor="black",
                    linewidth=0.4,
                )
                bottom = [lhs + rhs for lhs, rhs in zip(bottom, values)]
            axis.set(
                ylabel="Fraction of query states",
                title=f"State utilization, tolerance {primary:g}",
                ylim=(0.0, 1.02),
            )
            axis.tick_params(axis="x", labelrotation=70)
            place_legend_outside(axis)
            save_figure(figure, figures, "state_utilization")
            plt.close(figure)

        figure, axes = plt.subplots(1, 3, figsize=(13, 4))
        for algorithm in ("local_idw", "kkt_linear"):
            medians = []
            reductions = []
            errors = []
            for tolerance in tolerances:
                group = [
                    row
                    for row in adaptive
                    if row["algorithm"] == algorithm
                    and float(row["relative_tolerance"]) == tolerance
                ]
                medians.append(median([finite_float(row, "wall_speedup") for row in group]))
                reductions.append(
                    median([finite_float(row, "exact_call_reduction") for row in group])
                )
                errors.append(
                    max(
                        (finite_float(row, "max_normalized_error") for row in group),
                        default=math.nan,
                    )
                )
            style = {
                "color": METHOD_COLORS[algorithm],
                "linestyle": METHOD_LINESTYLES[algorithm],
                "marker": METHOD_MARKERS[algorithm],
                "label": method_label(algorithm),
            }
            axes[0].semilogx(tolerances, medians, **style)
            axes[1].semilogx(tolerances, reductions, **style)
            axes[2].loglog(tolerances, errors, **style)
        axes[0].axhline(2.0, color="black", linestyle="--", linewidth=0.8)
        axes[1].axhline(0.5, color="black", linestyle="--", linewidth=0.8)
        axes[2].axhline(1.0, color="black", linestyle="--", linewidth=0.8)
        axes[0].set(xlabel="Relative tolerance", ylabel="Median wall speedup")
        axes[1].set(xlabel="Relative tolerance", ylabel="Median exact-call reduction")
        axes[2].set(xlabel="Relative tolerance", ylabel="Worst normalized error")
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.08),
            ncol=2,
        )
        save_figure(figure, figures, "tolerance_comparison")
        plt.close(figure)


def validate_suite(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="thermochimica-adaptive-smoke-") as temporary:
        run_args = argparse.Namespace(
            exe=args.exe,
            tier="smoke",
            study="all",
            output=temporary,
            repetitions=1,
            no_prime=True,
            mpiexec=args.mpiexec,
            exec_prefix=args.exec_prefix,
            skip_plots=False,
            fail_fast=True,
        )
        output = run_suite(run_args)
        rows = [
            row
            for row in load_csv(output / "runs.csv")
            if row["mode"] == "adaptive" and row["stage"] == "query"
        ]
        capability = [
            row for row in rows if row["study"] == "capability_comparison"
        ]
        if {row["surrogate_model"] for row in capability} != {
            "local_idw",
            "kkt_linear",
        }:
            raise AssertionError("Smoke comparison did not run both surrogate models")
        if any(int(row["audit_failures"]) != 0 for row in capability):
            raise AssertionError("Smoke capability case reported an audit failure")
        errors = load_csv(output / "accuracy.csv")
        if not errors or any(not math.isfinite(float(row["max_absolute_error"])) for row in errors):
            raise AssertionError("Smoke accuracy results are missing or non-finite")
        if any(
            not list((output / "figures").glob(f"*.{extension}"))
            for extension in ("pdf", "svg", "png")
        ):
            raise AssertionError("Smoke validation did not generate PDF, SVG, and PNG figures")
        for name in (
            "performance_profile_tolerance_0.0001",
            "data_profile_tolerance_0.0001",
            "work_precision",
            "state_utilization",
            "tolerance_comparison",
        ):
            for extension in ("pdf", "svg", "png"):
                if not (output / "figures" / f"{name}.{extension}").is_file():
                    raise AssertionError(
                        f"Smoke validation did not generate {name}.{extension}"
                    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    subparsers = command.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one benchmark tier")
    run.add_argument("--tier", choices=("smoke", "quick", "full"), required=True)
    run.add_argument("--study", default="all", help="study name or 'all'")
    run.add_argument("--exe", required=True, help="Chemical Reactions MOOSE executable")
    run.add_argument("--output", help="result directory; defaults beneath results/")
    run.add_argument("--repetitions", type=int, help="override manifest repetitions")
    run.add_argument("--no-prime", action="store_true", help="skip unmeasured priming runs")
    run.add_argument("--mpiexec", default="mpiexec", help="MPI launcher")
    run.add_argument(
        "--exec-prefix",
        help="command placed immediately before the MOOSE executable, such as moose-dev-exec",
    )
    run.add_argument(
        "--skip-plots",
        action="store_true",
        help="defer plot generation for environments without matplotlib",
    )
    run.add_argument(
        "--fail-fast", action="store_true", help="stop instead of recording a failed configuration"
    )

    plot = subparsers.add_parser("plot", help="regenerate plots from benchmark CSV files")
    plot.add_argument("--input", required=True, help="result directory")

    report = subparsers.add_parser("report", help="regenerate capability reports from CSV files")
    report.add_argument("--input", required=True, help="result directory")

    validate = subparsers.add_parser("validate", help="run the smoke validation")
    validate.add_argument("--exe", required=True, help="Chemical Reactions MOOSE executable")
    validate.add_argument("--mpiexec", default="mpiexec", help="MPI launcher")
    validate.add_argument(
        "--exec-prefix",
        help="command placed immediately before the MOOSE executable, such as moose-dev-exec",
    )
    return command


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "run":
            output = run_suite(args)
            print(output)
        elif args.command == "plot":
            plot_results(Path(args.input).resolve())
        elif args.command == "report":
            report_results(Path(args.input).resolve())
        else:
            validate_suite(args)
            print("Adaptive Thermochimica benchmark smoke validation passed")
    except (AssertionError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
