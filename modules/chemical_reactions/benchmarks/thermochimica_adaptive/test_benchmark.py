#!/usr/bin/env python3

import math
from pathlib import Path
import tempfile
import unittest

import benchmark


class BenchmarkTests(unittest.TestCase):
    def test_reader_facing_method_labels(self):
        self.assertEqual(benchmark.method_label("exact_gem"), "Full GEM")
        self.assertEqual(
            benchmark.method_label("local_idw"), "Adaptive local interpolation"
        )
        self.assertEqual(
            benchmark.method_label("kkt_linear"), "Adaptive KKT sensitivity"
        )

    def test_capability_gate_uses_exhaustive_accuracy(self):
        status, reasons = benchmark.capability_status(1.01, 0.0, 0.0, 0.9, 10.0)
        self.assertEqual(status, "FAIL_ACCURACY")
        self.assertIn("accuracy or invariant requirement failed", reasons)

    def test_utilization_is_a_partition(self):
        row = {
            "states_median": "100",
            "exact_reuse_hits_median": "10",
            "surrogate_hits_median": "50",
            "audits_median": "5",
        }
        self.assertEqual(
            benchmark.utilization_counts(row),
            (100.0, 10.0, 50.0, 5.0, 35.0),
        )
        self.assertEqual(
            benchmark.query_state_percent(row, "surrogate_hits_median"),
            50.0,
        )

    def test_profile_keeps_invalid_problems_in_denominator(self):
        _, fractions = benchmark.profile_curve([1.0, math.inf], 2)
        self.assertEqual(fractions[-1], 0.5)

    def test_grid_aligned_query_is_rejected(self):
        config = {
            "case": "binary_comparison",
            "problem_id": "aligned",
            "composition_min": 0.2,
            "composition_max": 0.8,
            "temporal_displacement": 0.006,
            "mesh": 100,
        }
        with self.assertRaisesRegex(ValueError, "overlap exactly"):
            benchmark.validate_nonoverlapping_trajectory(config)

    def test_exact_key_reuses_tolerances_but_separates_trajectories(self):
        base = {
            "study": "capability_comparison",
            "case": "binary_comparison",
            "problem_id": "hcp-n100",
            "composition_min": 0.25,
            "composition_max": 0.45,
            "temporal_displacement": 1e-4,
            "mesh": 100,
            "chemical_elements": 2,
            "warm_start": "previous_solve",
            "threads": 1,
            "ranks": 1,
            "relative_tolerance": 1e-4,
            "surrogate_model": "local_idw",
        }
        changed_tolerance = dict(
            base, relative_tolerance=1e-5, surrogate_model="kkt_linear"
        )
        changed_trajectory = dict(base, problem_id="bcc-n100", composition_min=0.72)
        self.assertEqual(
            benchmark.exact_key(base), benchmark.exact_key(changed_tolerance)
        )
        self.assertNotEqual(
            benchmark.exact_key(base), benchmark.exact_key(changed_trajectory)
        )

    def test_absolute_tolerance_uses_exact_reproducibility(self):
        header = "id,x," + ",".join(benchmark.CASE_OUTPUTS["binary_comparison"])
        zeros = ["0"] * len(benchmark.CASE_OUTPUTS["binary_comparison"])
        warm = ["0", "0", *zeros]
        cold = list(warm)
        output_index = 2 + benchmark.CASE_OUTPUTS["binary_comparison"].index("hcp_amount")
        cold[output_index] = "1e-8"
        with tempfile.TemporaryDirectory() as temporary:
            warm_path = Path(temporary) / "warm.csv"
            cold_path = Path(temporary) / "cold.csv"
            warm_path.write_text(header + "\n" + ",".join(warm) + "\n", encoding="utf-8")
            cold_path.write_text(header + "\n" + ",".join(cold) + "\n", encoding="utf-8")
            tolerances = benchmark.calibrate_absolute_tolerances(
                "binary_comparison", warm_path, cold_path
            )
        self.assertAlmostEqual(tolerances["hcp_amount"], 1e-7)

    def test_exact_calibration_uses_a_valid_surrogate_enum(self):
        config = benchmark.expand_study(
            "capability_comparison",
            {
                "meshes": [100],
                "tolerances": [1e-4],
                "surrogate_models": ["local_idw"],
                "problems": [
                    {
                        "id": "hcp",
                        "composition_min": 0.25,
                        "composition_max": 0.45,
                    }
                ],
            },
        )[0]
        config["warm_start"] = "none"
        config["surrogate_model"] = "local_idw"
        command = benchmark.command_for(
            Path("/tmp/chemical_reactions-opt"),
            "mpiexec",
            None,
            config,
            "exact",
            Path("/tmp/calibration"),
        )
        self.assertIn(
            "ChemicalComposition/thermo/surrogate_model=local_idw", command
        )
        self.assertFalse(any("surrogate_model=calibration" in value for value in command))

    def test_parallel_thread_case_uses_launcher_for_one_rank(self):
        config = {
            "study": "parallel",
            "case": "binary_smooth",
            "mesh": 100,
            "chemical_elements": 2,
            "relative_tolerance": 1e-4,
            "neighbors": 8,
            "cache_capacity": 10000,
            "audit_interval": 100,
            "warm_start": "previous_solve",
            "surrogate_model": "local_idw",
            "threads": 4,
            "ranks": 1,
        }
        command = benchmark.command_for(
            Path("/tmp/chemical_reactions-opt"),
            "/usr/bin/srun",
            "/tmp/moose-dev-exec",
            config,
            "adaptive",
            Path("/tmp/parallel"),
        )
        self.assertEqual(
            command[:4],
            ["/usr/bin/srun", "-n", "1", "/tmp/moose-dev-exec"],
        )

    def test_binary_smooth_trajectory_is_not_grid_aligned(self):
        study = {
            "case": "binary_smooth",
            "axis": "mesh",
            "values": [10000, 100000],
        }
        configs = benchmark.expand_study("mesh", study)
        for config in configs:
            displacement_in_cells = (
                config["temporal_displacement"]
                * config["mesh"]
                / (config["composition_max"] - config["composition_min"])
            )
            self.assertFalse(
                math.isclose(
                    displacement_in_cells,
                    round(displacement_in_cells),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            )

    def test_full_parallel_study_reaches_sixteen_threads_and_ranks(self):
        study = benchmark.load_manifest("full")["studies"]["parallel"]
        topologies = {
            (int(value["threads"]), int(value["ranks"]))
            for value in study["values"]
        }
        self.assertIn((16, 1), topologies)
        self.assertIn((1, 16), topologies)

    def test_full_parallel_fluoride_has_worker_local_idw_coverage(self):
        study = benchmark.load_manifest("full")["studies"]["parallel"]
        configs = benchmark.expand_study("parallel", study)
        fluoride = [
            config
            for config in configs
            if config["case"] == "multielement_fluoride"
        ]
        self.assertTrue(fluoride)
        self.assertTrue(all(config["mesh"] == 320 for config in fluoride))
        self.assertTrue(all(config["chemical_elements"] == 9 for config in fluoride))

    def test_underfilled_parallel_local_idw_is_rejected(self):
        study = {
            "case": "multielement_fluoride",
            "axis": "parallel",
            "mesh": 20,
            "chemical_elements": {"multielement_fluoride": 17},
            "neighbors": 8,
            "values": [{"threads": 16, "ranks": 1}],
        }
        with self.assertRaisesRegex(ValueError, "local IDW requires at least 9"):
            benchmark.expand_study("parallel", study)


if __name__ == "__main__":
    unittest.main()
