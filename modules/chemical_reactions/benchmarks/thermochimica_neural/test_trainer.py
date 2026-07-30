import csv
import json
import tempfile
import unittest
from pathlib import Path

import torch

from qualification import (
    MSFR_ELEMENTS,
    MSFR_PHASES,
    _archive_evaluation,
    _read_msfr_compositions,
    _msfr_output_spec,
    _telemetry_totals,
    _write_msfr_state_table,
)
from train_thermochimica_nn import train


class TrainerTest(unittest.TestCase):
    def _write_table(self, path, temperatures):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["temperature", "pressure", "Fe", "Cr", "gibbs", "bcc_amount", "fcc_fraction"]
            )
            for temperature in temperatures:
                for chromium in (0.1, 0.3, 0.5, 0.7, 0.9):
                    bcc_amount = max(0.0, 0.6 - chromium)
                    writer.writerow(
                        [
                            temperature,
                            1.0,
                            1.0 - chromium,
                            chromium,
                            -temperature * (1.0 + chromium),
                            bcc_amount,
                            1.0 if chromium >= 0.6 else 0.0,
                        ]
                    )

    def _specification(self, database):
        return {
            "database": database.name,
            "temperature_column": "temperature",
            "pressure_column": "pressure",
            "temperature_unit": "K",
            "pressure_unit": "bar",
            "composition_unit": "moles",
            "elements": ["Fe", "Cr"],
            "outputs": [
                {
                    "type": "system_gibbs",
                    "variable": "gibbs",
                    "extensive": True,
                    "nonnegative": False,
                    "fraction": False,
                    "transform": {"kind": "linear"},
                },
                {
                    "type": "phase",
                    "phase": "BCC_A2",
                    "variable": "bcc_amount",
                    "extensive": True,
                    "nonnegative": True,
                    "fraction": False,
                    "transform": {"kind": "log1p", "scale": 1e-8},
                },
                {
                    "type": "phase",
                    "phase": "FCC_A1",
                    "variable": "fcc_fraction",
                    "extensive": False,
                    "nonnegative": True,
                    "fraction": True,
                },
            ],
            "phase_gate": {
                "confidence_threshold": 0.99,
                "phases": [
                    {
                        "phase": "BCC_A2",
                        "amount_variable": "bcc_amount",
                        "presence_threshold": 1e-8,
                    }
                ],
            },
            "invariant_groups": [
                {
                    "name": "phase_fraction_sum",
                    "variables": ["fcc_fraction"],
                    "target": 1.0,
                    "tolerance": 1e-3,
                }
            ],
            "epochs": 20,
            "patience": 5,
        }

    def test_train_exports_schema_two_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            database = tmp_path / "database.dat"
            database.write_text("test database\n", encoding="utf-8")
            data = tmp_path / "exact.csv"
            self._write_table(data, (800.0, 1000.0, 1200.0, 1400.0))
            specification = self._specification(database)
            spec = tmp_path / "model.json"
            spec.write_text(json.dumps(specification), encoding="utf-8")
            archive = tmp_path / "model.pt"

            metadata = train(data, spec, archive, data)

            extra_files = {"metadata.json": ""}
            model = torch.jit.load(archive, _extra_files=extra_files)
            loaded_metadata = json.loads(extra_files["metadata.json"])
            self.assertEqual(tuple(model(torch.zeros((3, 4))).shape), (3, 6))
            self.assertEqual(loaded_metadata, metadata)
            self.assertEqual(loaded_metadata["schema_version"], 2)
            self.assertEqual(loaded_metadata["model_output_layout"]["regression_width"], 3)
            self.assertEqual(loaded_metadata["model_output_layout"]["phase_logit_count"], 1)
            self.assertEqual(loaded_metadata["model_output_layout"]["support_distance_offset"], 4)
            self.assertEqual(loaded_metadata["model_output_layout"]["support_distance_count"], 2)
            self.assertEqual(loaded_metadata["elements"], ["Fe", "Cr"])
            self.assertEqual(
                loaded_metadata["thermodynamic_units"]["system_gibbs_energy"], "J"
            )
            self.assertEqual(loaded_metadata["phase_gate"]["phases"][0]["output_index"], 1)
            self.assertEqual(loaded_metadata["invariant_groups"][0]["output_indices"], [2])
            self.assertEqual(loaded_metadata["outputs"][1]["transform"]["kind"], "log1p")
            self.assertEqual(len(loaded_metadata["support"]["assemblages"]), 2)
            self.assertTrue(
                all(item["radius"] > 0.0 for item in loaded_metadata["support"]["assemblages"])
            )
            self.assertTrue(loaded_metadata["database_sha256"])
            evaluation = _archive_evaluation(
                data, archive, specification, metadata
            )
            self.assertEqual(evaluation["rows"], 20)
            self.assertEqual(evaluation["all_row_metrics"]["gibbs"]["rows"], 20)
            self.assertEqual(
                evaluation["accepted_rows"] + sum(evaluation["rejections"].values()),
                evaluation["rows"],
            )

    def test_explicit_validation_does_not_expand_training_domain(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            database = tmp_path / "database.dat"
            database.write_text("test database\n", encoding="utf-8")
            data = tmp_path / "train.csv"
            validation = tmp_path / "validation.csv"
            self._write_table(data, (800.0, 1000.0))
            self._write_table(validation, (1400.0, 1600.0))
            spec = tmp_path / "model.json"
            spec.write_text(json.dumps(self._specification(database)), encoding="utf-8")

            metadata = train(data, spec, tmp_path / "model.pt", validation)

            self.assertEqual(metadata["split"]["kind"], "explicit")
            self.assertEqual(metadata["split"]["training_rows"], 10)
            self.assertEqual(metadata["split"]["validation_rows"], 10)
            self.assertLess(metadata["input_upper_bounds"][0], 1.5)
            self.assertEqual(metadata["support"]["anchor_count"], 10)
            self.assertEqual(len(metadata["support"]["assemblages"]), 2)

    def test_support_anchor_budget_is_assemblage_stratified(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            database = tmp_path / "database.dat"
            database.write_text("test database\n", encoding="utf-8")
            data = tmp_path / "exact.csv"
            self._write_table(data, (800.0, 1000.0, 1200.0, 1400.0))
            specification = self._specification(database)
            specification["support"] = {"max_anchors": 4}
            spec = tmp_path / "model.json"
            spec.write_text(json.dumps(specification), encoding="utf-8")

            metadata = train(data, spec, tmp_path / "model.pt", data)

            self.assertEqual(metadata["support"]["training_rows"], 20)
            self.assertEqual(metadata["support"]["anchor_count"], 4)
            self.assertEqual(
                [item["anchor_count"] for item in metadata["support"]["assemblages"]],
                [2, 2],
            )


class QualificationSpecificationTest(unittest.TestCase):
    def test_worker_telemetry_is_reduced_to_numeric_evidence(self):
        body = (
            "states=16, batches=1, exact_solves=4, surrogate_hits=12, "
            "rejections=(phase:0,geometry:0,error:1,invariant:2,invalid_state:0), "
            "audits=3, audit_failures=0, neural_batches=1, neural_out_of_bounds=4, "
            "neural_support_rejections=5, neural_phase_rejections=6, "
            "neural_disabled_workers=0, neural_inference_time=0.002 s, "
            "worker_solve_time=0.02 s"
        )

        totals = _telemetry_totals([body, body])

        self.assertEqual(totals["states"], 32)
        self.assertEqual(totals["exact_solves"], 8)
        self.assertEqual(totals["invariant_rejections"], 4)
        self.assertEqual(totals["neural_support_rejections"], 10)
        self.assertAlmostEqual(totals["neural_inference_time"], 0.004)
        self.assertAlmostEqual(totals["worker_solve_time"], 0.04)

    def test_msfr_endpoint_compositions_are_normalized_and_positive(self):
        for composition in _read_msfr_compositions():
            self.assertAlmostEqual(sum(composition.values()), 1.0, places=12)
            self.assertTrue(all(composition[element] > 0.0 for element in MSFR_ELEMENTS))

    def test_msfr_sobol_states_are_normalized_and_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            table = Path(temporary) / "states.csv"
            _write_msfr_state_table(table, 16, 71)
            with table.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 16)
            for row in rows:
                self.assertAlmostEqual(
                    sum(float(row[element]) for element in MSFR_ELEMENTS), 1.0, places=12
                )
                self.assertLessEqual(850.0, float(row["temperature"]))
                self.assertLessEqual(float(row["temperature"]), 1150.0)
                self.assertLessEqual(1.0, float(row["pressure"]))
                self.assertLessEqual(float(row["pressure"]), 3.0)
                self.assertLessEqual(0.95, float(row["redox_factor"]))
                self.assertLessEqual(float(row["redox_factor"]), 1.05)

    def test_msfr_output_spec_has_complete_coupled_groups(self):
        outputs, groups = _msfr_output_spec()
        variables = [output["variable"] for output in outputs]
        self.assertEqual(len(variables), len(set(variables)))
        self.assertEqual(
            groups[0]["variables"],
            [f"{prefix}_fraction" for prefix, _ in MSFR_PHASES],
        )
        self.assertEqual(len(groups), 1 + len(MSFR_ELEMENTS))
        for group in groups:
            self.assertEqual(group["target"], 1.0)
            self.assertEqual(group["tolerance"], 1e-3)
            self.assertTrue(set(group["variables"]).issubset(variables))


if __name__ == "__main__":
    unittest.main()
