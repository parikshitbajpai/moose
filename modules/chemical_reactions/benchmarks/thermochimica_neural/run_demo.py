#!/usr/bin/env python3
"""Generate, train, and compare the neural prototype demonstrations."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from train_thermochimica_nn import train


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "modules/chemical_reactions/chemical_reactions-opt"
HERE = Path(__file__).resolve().parent


def _run(arguments: list[str]) -> None:
    subprocess.run([str(APP), *arguments], cwd=ROOT, check=True)


def fe_cr(work: Path) -> None:
    exact_base = work / "fe_cr_exact"
    _run(["-i", str(HERE / "fe_cr.i"), f"Outputs/file_base={exact_base}"])
    data = exact_base.with_name(exact_base.name + "_samples_0002.csv")
    archive = work / "fe_cr.pt"
    train(data, HERE / "fe_cr.json", archive)
    _run(
        [
            "-i",
            str(HERE / "fe_cr.i"),
            "ChemicalComposition/thermo/acceleration=adaptive",
            "ChemicalComposition/thermo/surrogate_model=neural",
            f"ChemicalComposition/thermo/surrogate_archive={archive}",
            f"Outputs/file_base={work / 'fe_cr_neural'}",
        ]
    )


def fluoride_gas(work: Path) -> None:
    case = (
        ROOT
        / "modules/chemical_reactions/benchmarks/thermochimica_adaptive/cases/multielement_fluoride.i"
    )
    override = HERE / "fluoride_gas.i"
    exact_base = work / "fluoride_gas_exact"
    _run(
        [
            "--allow-unused",
            "--n-threads=4",
            "-i",
            str(case),
            str(override),
            "Mesh/gen/nx=400",
            "Mesh/gen/xmax=0.2",
            "ChemicalComposition/thermo/elements=U Zr F Be Li",
            "ChemicalComposition/thermo/acceleration=exact",
            f"Outputs/file_base={exact_base}",
        ]
    )
    data = sorted(work.glob(exact_base.name + "_samples_*.csv"))[-1]
    archive = work / "fluoride_gas.pt"
    train(data, HERE / "fluoride_gas.json", archive)
    _run(
        [
            "--allow-unused",
            "--n-threads=4",
            "-i",
            str(case),
            str(override),
            "Mesh/gen/nx=400",
            "Mesh/gen/xmin=0.00025",
            "Mesh/gen/xmax=0.19975",
            "ChemicalComposition/thermo/elements=U Zr F Be Li",
            "ChemicalComposition/thermo/acceleration=adaptive",
            "ChemicalComposition/thermo/surrogate_model=neural",
            f"ChemicalComposition/thermo/surrogate_archive={archive}",
            "ChemicalComposition/thermo/surrogate_relative_tolerance=1e-3",
            "ChemicalComposition/thermo/surrogate_audit_interval=20",
            f"Outputs/file_base={work / 'fluoride_gas_neural'}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("fe_cr", "fluoride_gas", "all"))
    parser.add_argument("--workdir", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.workdir.mkdir(parents=True, exist_ok=True)
    if arguments.case in ("fe_cr", "all"):
        fe_cr(arguments.workdir)
    if arguments.case in ("fluoride_gas", "all"):
        fluoride_gas(arguments.workdir)


if __name__ == "__main__":
    main()
