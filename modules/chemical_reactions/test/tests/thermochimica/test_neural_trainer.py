"""Expose the neural benchmark's focused trainer tests to the MOOSE harness."""

import sys
from pathlib import Path


BENCHMARK = (
    Path(__file__).resolve().parents[3] / "benchmarks" / "thermochimica_neural"
)
sys.path.insert(0, str(BENCHMARK))

from test_trainer import *  # noqa: E402,F403
