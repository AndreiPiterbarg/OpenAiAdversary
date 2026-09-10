"""Diagnostic denominator and freeze checks; no inference or cluster jobs."""
import json
from pathlib import Path

import pytest

from adversary.core.factors import Cell
from adversary.probe.kill import MinimalPair
from domains.swe_agents.scripts.interactive_adversary import register, run_registered, summarize
from tests.test_tier1_grounding import grounded  # noqa: F401


def test_four_cells_five_repetitions_and_immutable_output(grounded: tuple, tmp_path: Path) -> None:  # noqa: F811
    draft = grounded[3]
    draft = draft.model_copy(update={
        "clauses": ("rewrite", "second"), "cell": Cell(levels={"rewrite": "on", "second": "on"}),
        "pair": MinimalPair(control=Cell(levels={"rewrite": "off", "second": "on"}),
                            treatment=Cell(levels={"rewrite": "on", "second": "on"})),
    })
    out = tmp_path / "run"
    receipt = register(draft, [{"key": "a"}, {"key": "b"}, {"key": "c"}], out)
    assert len(receipt["runs"]) == 60
    assert len({tuple(row["cell"].items()) for row in receipt["runs"]}) == 4
    later = register(draft, [{"key": "a"}], tmp_path / "later", seed_base=3000)
    assert {row["seed"] for row in later["runs"]} == set(range(3000, 3005))
    assert not {row["seed"] for row in receipt["runs"]} & {
        row["seed"] for row in later["runs"]
    }
    assert all(row["seed"] == 3000 + row["repetition"] for row in later["runs"])
    calibration = register(draft, [{"key": "a"}, {"key": "b"}, {"key": "c"}],
                           tmp_path / "calibration", seed_base=4000, calibration_only=True)
    assert len(calibration["runs"]) == 15
    assert calibration["never_pool_with_perturbation_arm"] is True
    assert all(row["cell_index"] == 0 for row in calibration["runs"])
    assert calibration["engineering_headroom_gate"]["all_five_attributable_required"] is True
    for invalid in (-1, True, 2**31 - 4, "3000"):
        with pytest.raises(ValueError, match="seed base"):
            register(draft, [{"key": "a"}], tmp_path / "invalid", seed_base=invalid)
    with pytest.raises(FileExistsError):
        register(draft, [{"key": "a"}], out)
    receipt["draft"]["hypothesis"] = "tampered"
    (out / "registration.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="digest"):
        run_registered(out, lambda *_: pytest.fail("must not execute"))


def test_unknown_and_censored_runs_do_not_become_group_failure() -> None:
    rows = [{"task": {"key": "a"}, "cell_index": 0, "diagnostic_passed": False}
            for _ in range(5)]
    complete = summarize(rows)
    assert complete["groups"][0]["task_failure"] is True
    rows[0]["diagnostic_passed"] = None
    result = summarize(rows)
    assert result["unknown"] == 1
    assert result["planned"] == 5
    assert result["groups"][0]["task_failure"] is None
    rows[0]["diagnostic_passed"] = False
    rows[0]["budget_exhausted"] = True
    assert summarize(rows)["groups"][0]["task_failure"] is None


def test_unrealized_active_measurements_remain_unknown_in_full_denominator() -> None:
    rows = [{"id": f"{cell}-{r}", "task": {"key": "one"}, "cell_index": cell,
             "repetition": r, "diagnostic_passed": False, "status": "completed",
             "realized": cell == 0, "visible_changed": False}
            for cell in range(4) for r in range(5)]
    result = summarize(rows)
    assert result["planned"] == result["diagnostic_measured"] == 20
    assert result["attributable_known"] == 5 and result["unknown"] == 15
    assert result["visible_changed"] == 0
    assert result["groups"][0]["task_failure"] is True
    assert all(group["task_failure"] is None for group in result["groups"][1:])
    assert result["contrasts"][0]["additive_excess"] is None


def test_censored_and_missing_registered_runs_cannot_create_contrast() -> None:
    registered = [{"id": f"{cell}-{r}", "task": {"key": "one"}, "cell_index": cell,
                   "repetition": r} for cell in range(4) for r in range(5)]
    rows = [{**run, "diagnostic_passed": False, "realized": True, "status": "completed",
             "clause_exposure_status": "verified"}
            for run in registered[:-1]]
    rows[0]["budget_exhausted"] = True
    result = summarize(rows, registered_runs=registered)
    assert result["planned"] == 20 and result["diagnostic_measured"] == 19
    assert result["unknown"] == 2
    assert result["groups"][0]["task_failure"] is None
    assert result["contrasts"][0]["additive_excess"] is None


def test_complete_four_cells_export_descriptive_delta_and_excess() -> None:
    passes = [5, 4, 4, 1]
    rows = [{"task": {"key": "one"}, "cell_index": cell, "repetition": r,
             "diagnostic_passed": r < passes[cell], "realized": True,
             "visible_changed": cell != 0, "status": "completed",
             "clause_exposure_status": "verified"}
            for cell in range(4) for r in range(5)]
    result = summarize(rows)
    contrast = result["contrasts"][0]
    assert contrast["complete"]
    assert contrast["delta_a"] == pytest.approx(0.2)
    assert contrast["delta_b"] == pytest.approx(0.2)
    assert contrast["delta_all_on"] == pytest.approx(0.8)
    assert contrast["additive_excess"] == pytest.approx(0.4)
    assert contrast["confidence_interval"] is None and contrast["descriptive_only"]
    assert not any(result[field] for field in ("protected", "trained", "confirmed"))


def test_changed_control_is_not_attributable_identity() -> None:
    rows = [{"task": {"key": "one"}, "cell_index": 0, "repetition": r,
             "diagnostic_passed": True, "visible_changed": True} for r in range(5)]
    result = summarize(rows)
    assert result["diagnostic_measured"] == 5 and result["attributable_known"] == 0
    assert result["groups"][0]["task_failure"] is None


def test_rendered_schema_pair_example_has_exactly_one_changed_switch() -> None:
    from adversary.search.proposer import DRAFT_SCHEMA

    start = DRAFT_SCHEMA.index('"pair": ') + len('"pair": ')
    example, _ = json.JSONDecoder().raw_decode(DRAFT_SCHEMA[start:])
    pair = MinimalPair(control=Cell(levels=example["control"]),
                       treatment=Cell(levels=example["treatment"]))
    assert len(pair.control.levels) == 2
    assert pair.factor == "<first_clause>"
