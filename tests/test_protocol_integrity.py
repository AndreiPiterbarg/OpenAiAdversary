"""Every registered experiment in experiments/ must have an intact chain."""

from pathlib import Path

import pytest

from adversary.protocol import verify

ROOT = Path(__file__).resolve().parents[1] / "experiments"
REGISTERED = sorted(p.parent for p in ROOT.glob("*/registration.json"))


@pytest.mark.parametrize("directory", REGISTERED, ids=lambda p: p.name)
def test_registered_experiment_is_intact(directory: Path):
    assert verify(directory) == []


def test_unregistered_experiments_have_no_results():
    for d in ROOT.glob("*"):
        if d.is_dir() and not d.name.startswith("_") and not (d / "registration.json").exists():
            results = d / "results"
            assert not results.exists() or not any(results.iterdir()), (
                f"{d.name} has results but no registration"
            )
