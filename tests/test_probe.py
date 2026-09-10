from pathlib import Path

import pytest

from adversary.core.factors import Cell
from adversary.core.model import LicenseClass
from adversary.probe.kill import KillRecord, MeasuredOutcome, MinimalPair, Prediction
from adversary.probe.library import LicenseError, ProbeLibrary
from adversary.probe.probe import Probe, ProbeProvenance
from adversary.probe.program import ProgramError, ProgramKind, ProgramSource

TOY_SOURCE = (Path(__file__).parent / "toy_programs.py").read_text()


def pair() -> MinimalPair:
    return MinimalPair(
        control=Cell(levels={"operation": "mul", "operand_size": "large", "distractor": "none"}),
        treatment=Cell(
            levels={"operation": "mul", "operand_size": "large", "distractor": "present"}
        ),
    )


def measured(effect: float, p: float) -> MeasuredOutcome:
    return MeasuredOutcome(
        control_n=20,
        control_failures=2,
        treatment_n=20,
        treatment_failures=int(2 + 20 * effect),
        effect=effect,
        ci_low=effect - 0.1,
        ci_high=effect + 0.1,
        p_value=p,
        episode_ids=("ep_1",),
        store_digest="d",
    )


def test_minimal_pair_must_differ_in_exactly_one_factor():
    with pytest.raises(ValueError):
        MinimalPair(
            control=Cell(levels={"a": "0", "b": "0"}), treatment=Cell(levels={"a": "1", "b": "1"})
        )
    with pytest.raises(ValueError):
        MinimalPair(control=Cell(levels={"a": "0"}), treatment=Cell(levels={"a": "0", "b": "1"}))
    assert pair().factor == "distractor"


def test_kill_record_verdict_must_follow_measurement():
    prediction = Prediction(min_effect=0.3, statement="treatment fails 30 points more")
    strong, weak = measured(0.6, 0.001), measured(0.05, 0.6)
    assert KillRecord.verdict_for(strong, prediction) == "survived"
    assert KillRecord.verdict_for(weak, prediction) == "killed"
    assert strong.test == "fisher" and not strong.paired
    with pytest.raises(ValueError):
        KillRecord(
            id="k",
            hypothesis="h",
            pair=pair(),
            prediction=prediction,
            measured=weak,
            verdict="survived",
        )
    with pytest.raises(ValueError):
        MeasuredOutcome(**{**strong.model_dump(), "episode_ids": ()})


def test_verifier_program_may_not_import_models_or_the_network():
    body = (
        "from adversary.core.verify import Verifier\n"
        "class V(Verifier):\n    def verify(self, t, o):\n        return None\n"
    )
    for head in (
        "from adversary.core.model import LanguageModel\n",
        "import urllib.request\n",
        "from adversary.core import LanguageModel\n",
    ):
        source = head + body
        bad = ProgramSource(kind=ProgramKind.VERIFIER, entrypoint="V", source=source)
        assert bad.check(), source
        with pytest.raises(ProgramError):
            bad.load()
    good = ProgramSource(kind=ProgramKind.VERIFIER, entrypoint="ToyVerifier", source=TOY_SOURCE)
    assert good.check() == [] and good.load().__name__ == "ToyVerifier"
    with pytest.raises(ProgramError):
        ProgramSource(
            kind=ProgramKind.GENERATOR, entrypoint="ToyVerifier", source=TOY_SOURCE
        ).load()


def make_probe(license: LicenseClass | None = None, cell: Cell | None = None) -> Probe:
    gen = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint="ToyGenerator", source=TOY_SOURCE)
    ver = ProgramSource(kind=ProgramKind.VERIFIER, entrypoint="ToyVerifier", source=TOY_SOURCE)
    return Probe(
        id=Probe.make_id("h", gen, ver),
        hypothesis="h",
        generator=gen,
        verifier=ver,
        cell=cell or Cell(levels={"operation": "mul", "distractor": "present"}),
        pair=pair(),
        prediction=Prediction(min_effect=0.3, statement="s"),
        provenance=ProbeProvenance(
            factor_space="fp", authored_by="m" if license else None, author_license=license
        ),
    )


def test_probe_validation_and_library_gate(tmp_path):
    probe = make_probe()
    assert probe.shippable
    with pytest.raises(ValueError):
        probe.with_(cell=Cell(levels={"distractor": "none"}))  # treatment does not realise it
    with pytest.raises(ValueError):
        make_probe(
            cell=Cell(levels={"operation": "mul"})
        )  # the flipped factor is not in the region
    library = ProbeLibrary(tmp_path)
    library.add(probe)
    assert probe.id in library and library.get(probe.id) == probe and len(library) == 1
    restricted = make_probe(LicenseClass.RESTRICTED)
    assert not restricted.shippable
    with pytest.raises(LicenseError):
        library.add(restricted)
