"""The mechanisms amendments A3 to A10 of the E1 protocol rely on."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from adversary.core.model import Message
from adversary.core.trajectory import Trajectory
from adversary.domain.contract import SolvabilityCertificate
from adversary.protocol import (
    PlantManifest,
    PreregistrationError,
    decide,
    leaked_canaries,
    parse_sidecar,
    recall,
    register,
    relative_recall,
    seal_results,
    verify,
    verify_sidecar,
)
from adversary.search.context import SearchContext
from adversary.search.referee import Referee, floor_gap
from adversary.stats import (
    BudgetLedger,
    Prices,
    branch_agreement,
    estimate_excess,
    ledger_of,
    mobius_synergy,
    permutation_null,
    species_estimate,
    validity_check,
    yield_curve,
    zero_failure_bound,
)
from adversary.stats.clauses import ClauseAudit
from tests.test_stats import synthetic_episodes
from tests.toy_domain import SPACE

ROOT = Path(__file__).resolve().parents[1]


# ---- A4: balanced designs ---------------------------------------------------------------------




# ---- A4: leave-cell-out predictions ------------------------------------------------------------


def test_leave_cell_out_prediction_is_not_pulled_by_the_cell():
    eps = synthetic_episodes(n_per_cell=30)
    hot = Cell(levels={"a": "1", "b": "1", "c": "1"})
    shared = estimate_excess(eps, [hot], bootstrap=0, leave_cell_out=False)[0]
    held_out = estimate_excess(eps, [hot], bootstrap=0, leave_cell_out=True)[0]
    assert held_out.excess > shared.excess  # the shared fit had absorbed part of the interaction
    assert held_out.n == shared.n == 30


# ---- A5: Möbius synergy ---------------------------------------------------------------------------


def test_mobius_synergy_matches_the_amendment_example():
    f = ("x", "y")
    rates = {
        frozenset(): 0.10,
        frozenset({"x"}): 0.30,
        frozenset({"y"}): 0.30,
        frozenset({"x", "y"}): 0.62,
    }
    m = mobius_synergy(f, rates, clause_audit=clause_audit(f), program_digest="a" * 64)
    assert m.synergy == pytest.approx(0.12) and m.highest_order_term == pytest.approx(0.12)
    assert m.terms['["x"]'] == pytest.approx(0.2) and m.rates["[]"] == 0.10
    three = ("x", "y", "z")
    rates3 = {
        frozenset(s): 0.1 + 0.1 * len(s)
        for s in map(
            frozenset,
            [(), ("x",), ("y",), ("z",), ("x", "y"), ("x", "z"), ("y", "z"), ("x", "y", "z")],
        )
    }
    assert mobius_synergy(
        three, rates3, clause_audit=clause_audit(three), program_digest="a" * 64
    ).synergy == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(ValueError):
        mobius_synergy(f, {frozenset(): 0.1}, clause_audit=clause_audit(f), program_digest="a" * 64)
    assert branch_agreement(0.55, 0.62).valid and not branch_agreement(0.40, 0.62).valid


# ---- A7: priority --------------------------------------------------------------------------------




# ---- A3: hazard-present floor ---------------------------------------------------------------------


def test_certificate_semantics_and_floor_gap():
    clean_only = SolvabilityCertificate(
        instance_id="i", method="construction", clean_passed=True, evidence="e"
    )
    assert clean_only.solvable and not clean_only.unrecoverable
    unrecoverable = SolvabilityCertificate(
        instance_id="i",
        method="construction",
        clean_passed=True,
        perturbations=("stale",),
        perturbed_runs=3,
        perturbed_passed=2,
        evidence="e",
    )
    recovered = unrecoverable.model_copy(update={"perturbed_passed": 3})
    assert not unrecoverable.solvable and unrecoverable.witness_failed and recovered.solvable
    assert not unrecoverable.unrecoverable
    assert floor_gap([unrecoverable, recovered]) == {"stale": 0.5}

    class Ref:
        def certify(self, instance):  # noqa: ANN001
            return unrecoverable

    instance = Instance(
        id="i", cell=Cell(levels={}), seed=0, spec={}, oracle={},
        provenance=Provenance(generator="test", generator_version="1", seed=0),
    )
    report = Referee(Ref()).admit([instance])
    assert (
        not report.admitted
        and report.unrecoverable == 0
        and report.witness_failed == 1
        and report.floor_gap == {"stale": 1.0}
    )


# ---- A8: plants, canaries, relative recall --------------------------------------------------------


def test_plant_manifest_seals_and_scores(tmp_path):
    cells = [
        Cell(levels={"a": "1"}),
        Cell(levels={"a": "1", "b": "1"}),
        Cell(levels={"a": "1", "b": "1", "c": "1"}),
        Cell(levels={"e": "1"}),
    ]
    plants = [PlantManifest.make_plant(c, 25.0, silent=i % 2 == 0) for i, c in enumerate(cells)]
    manifest = PlantManifest(experiment="e01", plants=tuple(plants), seeds=(1, 2))
    sha = manifest.seal(tmp_path / "plants.json")
    assert sha == hashlib.sha256((tmp_path / "plants.json").read_bytes()).hexdigest()
    modes = manifest.modes({c: 0.1 for c in cells})
    assert all(m.failure_rate == pytest.approx(0.25 / 0.9) for m in modes)
    # An exact region finds its plant; a narrower region refines and also finds; a broader
    # region merges; a region touching nothing misses.
    system = recall(
        [Cell(levels={"a": "1"}), Cell(levels={"a": "1", "b": "1", "c": "1", "d": "0"})], plants
    )
    oracle = recall(cells, plants)
    assert set(system.found) == {plants[0].id, plants[1].id, plants[2].id}
    assert system.merged == () and system.missed == (plants[3].id,)
    rel = relative_recall(system, oracle, plants)
    assert rel.by_order == {1: 0.5, 2: 1.0, 3: 1.0}
    assert rel.meets(0.8, [2, 3]) and not rel.meets(0.8, [1, 3])
    merged = recall([Cell(levels={"a": "1", "b": "1"})], plants)  # broader than the 3-way plant
    assert plants[2].id in merged.merged and merged.recall == pytest.approx(3 / 4)
    trajectories = [
        Trajectory(
            instance_id="t1",
            model_id="m",
            messages=(Message(role="user", content=f"hi {plants[0].canary}"),),
        ),
        Trajectory(
            instance_id="t2", model_id="m", messages=(Message(role="user", content="clean"),)
        ),
    ]
    assert leaked_canaries(plants, trajectories) == [(plants[0].id, "t1")]
    assert (
        zero_failure_bound(20, 0.9) == pytest.approx(3 / 18) and zero_failure_bound(0, 0.9) == 1.0
    )


def test_sidecar_file_entries_and_history(tmp_path):
    doc = tmp_path / "P.md"
    doc.write_text("head\nrecorded here:\n## 9. Amendments\nA1\n")
    plants = tmp_path / "plants.json"
    plants.write_text("{}")
    head_sha = hashlib.sha256(b"head\nrecorded here:\n").hexdigest()
    old_amend = hashlib.sha256(b"## 9. Amendments\nA1\n").hexdigest()
    side = tmp_path / "P.hashes"
    side.write_text(
        'prose preamble\n[registered]\nregion = start of file through the line ending "recorded here:"\n'
        f'sha256 = {head_sha}\n[amendments]\nregion = from the line "## 9. Amendments" to end of file\n'
        f"sha256 = {old_amend}\n[plants]\nfile = plants.json\nsha256 = {hashlib.sha256(b'{}').hexdigest()}\n"
    )
    entries, problems = verify_sidecar(doc, side)
    assert problems == [] and [e.name for e in entries] == ["registered", "amendments", "plants"]
    doc.write_text("head\nrecorded here:\n## 9. Amendments\nA1\nA2\n")
    assert any("[amendments] region" in p for p in verify_sidecar(doc, side)[1])
    new_amend = hashlib.sha256(b"## 9. Amendments\nA1\nA2\n").hexdigest()
    side.write_text(
        side.read_text()
        + f'\n[amendments]\nregion = from the line "## 9. Amendments" to end of file\nsha256 = {new_amend}\nnote = A2 appended\n'
    )
    entries, problems = verify_sidecar(doc, side)
    assert problems == [] and len([e for e in entries if e.name == "amendments"]) == 2
    side.write_text(
        side.read_text()
        + f'\n[registered]\nregion = start of file through the line ending "recorded here:"\nsha256 = {"0" * 64}\n'
    )
    assert any("may not change" in p for p in verify_sidecar(doc, side)[1])
    with pytest.raises(ValueError):
        parse_sidecar("[x]\nregion = a\nfile = b\nsha256 = c\n")


# ---- A6: survive_if band ----------------------------------------------------------------------------


PREREG = """title: "T"
question: "Q?"
hypothesis: "H"
kill_rules:
  - name: validity
    requires:
      - {metric: n, op: ">=", threshold: 300}
    all_of:
      - {metric: point, op: "<", threshold: 0.90}
    survive_if:
      - {metric: lower, op: ">=", threshold: 0.85}
    consequence: "oracle unusable"
analysis_plan: "audit"
"""


def test_validity_band_is_inconclusive_between_kill_and_pass(tmp_path):
    cases = {
        "kill": ({"n": 300, "point": 0.80, "lower": 0.75}, "killed"),
        "pass": ({"n": 300, "point": 0.95, "lower": 0.90}, "survived"),
        "band": ({"n": 300, "point": 0.92, "lower": 0.80}, "inconclusive"),
        "small": ({"n": 100, "point": 0.80, "lower": 0.70}, "inconclusive"),
    }
    for name, (metrics, outcome) in cases.items():
        d = tmp_path / name
        d.mkdir()
        (d / "preregistration.yaml").write_text(PREREG)
        (d / "config.yaml").write_text("x: 1\n")
        register(d)
        (d / "results").mkdir()
        (d / "results" / "metrics.json").write_text(json.dumps(metrics))
        seal_results(d)
        assert decide(d).outcome == outcome, name
        assert verify(d) == []
    with pytest.raises(PreregistrationError):
        register(tmp_path / "kill")


# ---- A9: species estimators ------------------------------------------------------------------------


def test_species_estimators_and_validity_check():
    est = species_estimate(
        100, counts=[1, 1, 1, 2, 2, 5, 9], incidence=[1, 1, 2, 2, 3, 3, 3], seeds=3
    )
    assert est.singletons == 3 and est.doubletons == 2 and est.observed_regions == 7
    assert est.discovery_probability == pytest.approx(0.03) and est.chao1_lower == pytest.approx(
        7 + 9 / 4
    )
    assert est.chao2_lower is not None and est.chao2_lower > 7 and est.source == "sentinel"
    rng = np.random.default_rng(0)
    streams = [list(rng.integers(1, 40, 200)) for _ in range(5)]
    check = validity_check(streams)
    assert check.seeds == 5 and 0 <= check.passed_seeds <= 5
    assert not validity_check([[1] * 100]).valid  # one seed cannot reach four passes


# ---- A10: ledger and yield curves -------------------------------------------------------------------


def test_ledger_and_yield_curve():
    eps = [e.model_copy(update={"build_seconds": 30.0}) for e in synthetic_episodes(n_per_cell=2)]
    ledger = ledger_of(eps).add("reference", 120.0).add("restore", 60.0)
    assert ledger.compute_seconds == pytest.approx(len(eps) * 30 + 180)
    spend = ledger.dollars(
        Prices(
            compute_dollars_per_hour=2.0,
            input_dollars_per_million_tokens=1.0,
            output_dollars_per_million_tokens=5.0,
        )
    )
    assert spend.llm_dollars == 0 and not spend.renormalise_to_dollars
    heavy = BudgetLedger(seconds={"run": 3600}, input_tokens=10_000_000).dollars(
        Prices(
            compute_dollars_per_hour=2.0,
            input_dollars_per_million_tokens=1.0,
            output_dollars_per_million_tokens=5.0,
        )
    )
    assert heavy.renormalise_to_dollars
    curve = yield_curve("A", 1, [(10.0, True), (20.0, False), (30.0, True)])
    assert curve.at(25.0) == 1 and curve.at(30.0) == 2 and curve.at(5.0) == 0


# ---- A8: permutation null -----------------------------------------------------------------------------


def test_permutation_null_rate_is_low_for_a_calibrated_procedure():
    eps = synthetic_episodes(n_per_cell=10)
    labels = [e.cell.label() for e in eps]
    outcomes = [e.failed for e in eps]

    def finds_region(labels_, outcomes_) -> bool:  # noqa: ANN001
        # declare a region when some label's failure rate exceeds 0.85 with >= 10 episodes
        by = {}
        for lab, out in zip(labels_, outcomes_, strict=True):
            by.setdefault(lab, []).append(out)
        return any(len(v) >= 10 and sum(v) / len(v) > 0.85 for v in by.values())

    assert finds_region(labels, outcomes)
    null = permutation_null(labels, outcomes, finds_region, permutations=100)
    assert null.rate < 0.2


# ---- sentinel context ----------------------------------------------------------------------------------


def test_sentinel_context_is_stripped():
    ctx = SearchContext(
        space=SPACE, transcripts=("t",), base_cell=Cell(levels={"operation": "add"})
    )
    stripped = ctx.stripped()
    assert stripped.transcripts == () and stripped.elites == () and stripped.hot_cells == ()
    assert stripped.base_cell == ctx.base_cell and stripped.space == SPACE


def clause_audit(factors):
    return ClauseAudit(
        program_digest="a" * 64,
        receipt_digest="b" * 64,
        clauses=factors,
        reviewer="authored arithmetic fixture",
        independent_switches=True,
        rationale="Known algebraic fixture; not a live admission receipt",
    )
