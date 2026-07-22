#!/usr/bin/env python3
"""Run and analyze the adaptive Thermochimica benchmark suite."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
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

CASE_FILES = {
    "binary_smooth": CASES / "binary_smooth.i",
    "binary_boundary": CASES / "binary_boundary.i",
    "multielement_fluoride": CASES / "multielement_fluoride.i",
    "multielement_heat_capacity": CASES / "multielement_heat_capacity.i",
}

CASE_OUTPUTS = {
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
}

ELEMENT_SETS = {
    2: "Li F",
    5: "Li Be F Zr U",
    9: "Li Be F Zr U Nd Ce La Cs",
    13: "Li Be F Zr U Nd Ce La Cs I Pu Rb Sr",
    17: "Li Be F Zr U Nd Ce La Cs I Pu Rb Sr Ba Pr Th Y",
    22: "Li Be F Zr U Nd Ce La Cs I Pu Rb Sr Ba Pr Th Y Ni Fe Cr K Na",
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
]
REJECTION_FIELDS = [
    "phase_rejections",
    "geometry_rejections",
    "error_rejections",
    "invariant_rejections",
    "invalid_state_rejections",
]
TIME_FIELDS = ["worker_solve_time", "packing_time", "ipc_time"]

RUN_FIELDS = [
    "run_id",
    "tier",
    "study",
    "case",
    "mode",
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
    "repetition",
    "axis",
    "axis_value",
    "output",
    "samples",
    "max_absolute_error",
    "rmse",
    "p95_absolute_error",
    "max_relative_error",
    "p95_relative_error",
    "relative_scale_floor",
]

FAILURE_FIELDS = [
    "tier",
    "study",
    "case",
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
        relative = [error / max(abs(value), scale_floor) for error, value in zip(absolute, expected)]
        records.append(
            {
                "run_id": run_id,
                "tier": tier,
                "study": config["study"],
                "case": config["case"],
                "repetition": repetition,
                "axis": config["axis"],
                "axis_value": config["axis_value"],
                "output": output,
                "samples": len(expected),
                "max_absolute_error": max(absolute, default=0.0),
                "rmse": math.sqrt(sum(value * value for value in absolute) / len(absolute)),
                "p95_absolute_error": percentile(absolute, 0.95),
                "max_relative_error": max(relative, default=0.0),
                "p95_relative_error": percentile(relative, 0.95),
                "relative_scale_floor": scale_floor,
            }
        )
    return records


def expand_study(name: str, study: dict[str, Any]) -> list[dict[str, Any]]:
    cases = study["case"] if isinstance(study["case"], list) else [study["case"]]
    configs = []
    for case in cases:
        for value in study["values"]:
            mesh = study.get("mesh", 200)
            if isinstance(mesh, dict):
                mesh = mesh[case]
            config = {
                "study": name,
                "case": case,
                "axis": study["axis"],
                "axis_value": value,
                "mesh": int(mesh),
                "chemical_elements": 22 if case.startswith("multielement_") else 2,
                "relative_tolerance": float(study.get("relative_tolerance", 1e-4)),
                "neighbors": 0,
                "cache_capacity": 10000,
                "audit_interval": int(study.get("audit_interval", 100)),
                "warm_start": "previous_solve",
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
        f"ChemicalComposition/thermo/warm_start={config['warm_start']}",
        f"ChemicalComposition/thermo/surrogate_relative_tolerance={config['relative_tolerance']}",
        f"ChemicalComposition/thermo/surrogate_neighbors={config['neighbors']}",
        f"ChemicalComposition/thermo/cache_max_entries={config['cache_capacity']}",
        f"ChemicalComposition/thermo/surrogate_audit_interval={config['audit_interval']}",
        f"Outputs/file_base={file_base}",
        f"--n-threads={config['threads']}",
    ]
    if config["case"].startswith("multielement_"):
        command.append(
            f"ChemicalComposition/thermo/elements={ELEMENT_SETS[config['chemical_elements']]}"
        )
    if config["ranks"] > 1:
        command = [mpiexec, "-n", str(config["ranks"])] + command
    return command


def run_process(command: list[str], log_path: Path) -> tuple[float, float | None, str]:
    peak_rss = None
    try:
        import psutil  # type: ignore
    except ImportError:
        psutil = None

    start = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        if psutil:
            monitored = psutil.Process(process.pid)
            peak_rss = 0
            while process.poll() is None:
                try:
                    processes = [monitored] + monitored.children(recursive=True)
                    peak_rss = max(peak_rss, sum(item.memory_info().rss for item in processes))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
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
    tier: str,
    config: dict[str, Any],
    mode: str,
    repetition: int,
    output: Path,
    commands: list[list[str]],
    prime: bool = False,
) -> dict[str, Any]:
    identity = f"{config['study']}-{config['case']}-{mode}-{slug(config['axis_value'])}-r{repetition}"
    if prime:
        identity += "-prime"
    file_base = output / "raw" / identity
    log_path = output / "logs" / f"{identity}.log"
    command = command_for(executable, mpiexec, config, mode, file_base)
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
            "mode": mode,
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
            row["meets_capability_gate"] = int(
                row["exact_call_reduction"] >= 0.5
                and row["worker_speedup"] >= 2.0
                and telemetry["audit_failures"] == 0
            )
        rows.append(row)
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def aggregate_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_rows = [row for row in rows if row["stage"] == "query"]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    keys = [
        "tier",
        "study",
        "case",
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
    ]
    for row in query_rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    numeric = [
        "wall_time",
        "peak_rss_bytes",
        "exact_solves",
        "gem_iterations",
        "exact_reuse_hits",
        "surrogate_hits",
        *REJECTION_FIELDS,
        "audits",
        "audit_failures",
        "cache_entries",
        "cache_saturated",
        "worker_solve_time",
        "wall_speedup",
        "worker_speedup",
        "exact_call_reduction",
    ]
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
        gate_values = [int(row.get("meets_capability_gate", 0) or 0) for row in group]
        record["meets_capability_gate"] = int(bool(gate_values) and all(gate_values))
        summary.append(record)
    return summary


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
                if config["exact_only"]:
                    continue
                if do_prime:
                    execute_once(
                        executable,
                        args.mpiexec,
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
                        )
                    )
            except RuntimeError as error:
                if args.fail_fast:
                    raise
                failures.append(
                    {
                        "tier": args.tier,
                        "study": config["study"],
                        "case": config["case"],
                        "axis": config["axis"],
                        "axis_value": config["axis_value"],
                        "mesh_elements": config["mesh"],
                        "chemical_elements": config["chemical_elements"],
                        "threads": config["threads"],
                        "ranks": config["ranks"],
                        "error": str(error),
                    }
                )

    write_csv(output / "runs.csv", RUN_FIELDS, rows)
    write_csv(output / "accuracy.csv", ACCURACY_FIELDS, accuracy)
    write_csv(output / "failures.csv", FAILURE_FIELDS, failures)
    summary = aggregate_runs(rows)
    summary_fields = list(summary[0]) if summary else []
    write_csv(output / "summary.csv", summary_fields, summary)
    with (output / "metadata.json").open("w", encoding="utf-8") as stream:
        json.dump(metadata(executable, args.tier, commands), stream, indent=2)
        stream.write("\n")
    plot_results(output)
    return output


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save_figure(figure: Any, directory: Path, name: str) -> None:
    figure.tight_layout()
    for extension in ("png", "svg"):
        figure.savefig(directory / f"{name}.{extension}", dpi=180)


def numeric_axis(row: dict[str, str]) -> float:
    value = row["axis_value"]
    if row["axis"] == "parallel":
        return float(row["threads"]) if int(row["ranks"]) == 1 else float(row["ranks"])
    return float(value)


def plot_results(directory: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError("Plot generation requires matplotlib") from error

    summary = load_csv(directory / "summary.csv")
    accuracy = load_csv(directory / "accuracy.csv")
    figures = directory / "figures"

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
            axes[0].loglog(
                [numeric_axis(row) for row in selected],
                [float(row["wall_time_median"]) for row in selected],
                "o-",
                label=mode,
            )
            axes[1].loglog(
                [numeric_axis(row) for row in selected],
                [float(row["worker_solve_time_median"]) for row in selected],
                "o-",
                label=mode,
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
            axes[0].plot(
                [numeric_axis(row) for row in selected],
                [float(row["worker_solve_time_median"]) for row in selected],
                "o-",
                label=mode,
            )
            axes[2].plot(
                [numeric_axis(row) for row in selected],
                [float(row["peak_rss_bytes_median"]) / (1024 * 1024) for row in selected],
                "o-",
                label=mode,
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
            fail_fast=True,
        )
        output = run_suite(run_args)
        rows = [
            row
            for row in load_csv(output / "runs.csv")
            if row["mode"] == "adaptive" and row["stage"] == "query"
        ]
        smooth = next(row for row in rows if row["case"] == "binary_smooth")
        boundary = next(row for row in rows if row["case"] == "binary_boundary")
        if int(smooth["surrogate_hits"]) < 1:
            raise AssertionError("Smooth smoke case did not produce a surrogate hit")
        if int(smooth["exact_solves"]) >= int(smooth["baseline_exact_solves"]):
            raise AssertionError("Smooth smoke case did not reduce exact GEM calls")
        if int(smooth["audit_failures"]) != 0:
            raise AssertionError("Smooth smoke case reported an audit failure")
        if int(boundary["phase_rejections"]) < 1:
            raise AssertionError("Boundary smoke case did not produce a phase rejection")
        errors = load_csv(output / "accuracy.csv")
        if not errors or any(not math.isfinite(float(row["max_absolute_error"])) for row in errors):
            raise AssertionError("Smoke accuracy results are missing or non-finite")
        if not list((output / "figures").glob("*.png")) or not list(
            (output / "figures").glob("*.svg")
        ):
            raise AssertionError("Smoke validation did not generate PNG and SVG figures")


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
        "--fail-fast", action="store_true", help="stop instead of recording a failed configuration"
    )

    plot = subparsers.add_parser("plot", help="regenerate plots from benchmark CSV files")
    plot.add_argument("--input", required=True, help="result directory")

    validate = subparsers.add_parser("validate", help="run the smoke validation")
    validate.add_argument("--exe", required=True, help="Chemical Reactions MOOSE executable")
    validate.add_argument("--mpiexec", default="mpiexec", help="MPI launcher")
    return command


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "run":
            output = run_suite(args)
            print(output)
        elif args.command == "plot":
            plot_results(Path(args.input).resolve())
        else:
            validate_suite(args)
            print("Adaptive Thermochimica benchmark smoke validation passed")
    except (AssertionError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
