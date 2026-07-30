import csv
import json
import tempfile
import unittest
from pathlib import Path

import torch

from train_thermochimica_nn import train


class TrainerTest(unittest.TestCase):
    def test_train_exports_self_contained_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            database = tmp_path / "database.dat"
            database.write_text("test database\n", encoding="utf-8")
            data = tmp_path / "exact.csv"
            with data.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["temperature", "pressure", "Fe", "Cr", "gibbs", "fraction"])
                for temperature in (800.0, 1000.0, 1200.0, 1400.0):
                    for chromium in (0.1, 0.3, 0.5, 0.7, 0.9):
                        writer.writerow(
                            [
                                temperature,
                                1.0,
                                1.0 - chromium,
                                chromium,
                                -temperature * (1.0 + chromium),
                                chromium,
                            ]
                        )

            specification = {
                "database": database.name,
                "temperature_column": "temperature",
                "pressure_column": "pressure",
                "temperature_unit": "K",
                "pressure_unit": "bar",
                "composition_unit": "moles",
                "elements": ["Fe", "Cr"],
                "outputs": [
                    {
                        "variable": "gibbs",
                        "extensive": True,
                        "nonnegative": False,
                        "fraction": False,
                    },
                    {
                        "variable": "fraction",
                        "extensive": False,
                        "nonnegative": True,
                        "fraction": True,
                    },
                ],
                "epochs": 20,
                "patience": 5,
            }
            spec = tmp_path / "model.json"
            spec.write_text(json.dumps(specification), encoding="utf-8")
            archive = tmp_path / "model.pt"

            metadata = train(data, spec, archive)

            extra_files = {"metadata.json": ""}
            model = torch.jit.load(archive, _extra_files=extra_files)
            loaded_metadata = json.loads(extra_files["metadata.json"])
            self.assertEqual(tuple(model(torch.zeros((3, 4))).shape), (3, 2))
            self.assertEqual(loaded_metadata, metadata)
            self.assertEqual(loaded_metadata["elements"], ["Fe", "Cr"])
            self.assertTrue(loaded_metadata["database_sha256"])


if __name__ == "__main__":
    unittest.main()
