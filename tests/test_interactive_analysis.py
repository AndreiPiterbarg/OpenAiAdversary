"""One-arm denominators, contamination and measured timing accounting."""
import json
from pathlib import Path

import pytest

from domains.swe_agents.scripts.interactive_analysis import analyze, calibration_gate


def fixture(root: Path, *, missing: bool = False) -> None:
    runs = [{"id": f"r{i}", "task": {"key": "task"}, "cell_index": 0,
             "repetition": i} for i in range(5)]
    (root / "registration.json").write_text(json.dumps({"runs": runs}))
    (root / "integrity-assessment.json").write_text('{"status":"valid"}')
    (root / "summary.json").write_text('{"elapsed_seconds":20}')
    for i, run in enumerate(runs):
        if missing and i == 4:
            continue
        path = root / run["id"]
        path.mkdir()
        row = {**run, "status": "completed", "diagnostic_passed": i < 2,
               "wall_seconds": i + 1, "usage": {"input_tokens": 10, "output_tokens": 5},
               "usage_unknown": False}
        (path / "result.json").write_text(json.dumps(row))


def test_denominator_usage_and_actual_elapsed(tmp_path: Path) -> None:
    fixture(tmp_path, missing=True)
    report = analyze(tmp_path)
    assert report["registered"] == 5
    assert report["exclusive_reasons"] == {
        "attributable_pass": 2, "attributable_failure": 2, "missing_terminal": 1,
    }
    assert report["task_cells"][0]["failure_fraction_bounds"] == [.4, .6]
    assert report["model_usage"]["input_tokens"] == 40
    assert report["model_usage"]["is_lower_bound"] is True
    assert report["batch"]["terminal_per_hour"] == 720
    assert report["episode_walls"]["p50_seconds"] == 2.5
    assert report["episode_walls"]["p90_seconds"] == pytest.approx(3.7)
    assert report["control_headroom"][0]["calibration_gate"]["eligible"] is False


def test_integrity_invalid_cannot_authorize_calibration(tmp_path: Path) -> None:
    fixture(tmp_path)
    assert analyze(tmp_path)["control_headroom"][0]["calibration_gate"]["eligible"] is True
    (tmp_path / "integrity-assessment.json").write_text(
        '{"status":"invalid","reason":"future gold commit available"}'
    )
    report = analyze(tmp_path)
    gate = report["control_headroom"][0]["calibration_gate"]
    assert gate["outcome_threshold_met"] is True
    assert gate["eligible"] is False
    assert report["causal_eligible"] is False
    assert report["task_cells"][0]["passes"] == 2
    assert report["integrity_assessment"]["reason"] == "future gold commit available"


def test_censoring_reason_is_exclusive_and_missing_elapsed_not_estimated(tmp_path: Path) -> None:
    fixture(tmp_path)
    p = tmp_path / "r0/result.json"
    row = json.loads(p.read_text())
    row.update(admission_status="rejected", budget_exhausted=True, diagnostic_passed=None,
               usage_unknown=True)
    p.write_text(json.dumps(row))
    (tmp_path / "summary.json").unlink()
    report = analyze(tmp_path)
    assert report["exclusive_reasons"]["admission_rejected"] == 1
    assert "budget_censored" not in report["exclusive_reasons"]
    assert sum(report["exclusive_reasons"].values()) == 5
    assert report["batch"]["terminal_per_hour"] is None
    assert report["model_usage"]["is_lower_bound"] is True


def test_duplicate_and_mismatched_assignments_refused(tmp_path: Path) -> None:
    fixture(tmp_path)
    p = tmp_path / "r0/result.json"
    row = json.loads(p.read_text())
    row["cell_index"] = 2
    p.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="registration"):
        analyze(tmp_path)


def test_calibration_is_fixed_five_execution_engineering_gate() -> None:
    assert calibration_gate({"complete": True, "executions": 5, "known": 5, "passes": 2})[
        "eligible"
    ]
    assert not calibration_gate({"complete": True, "executions": 4, "known": 4, "passes": 4})[
        "eligible"
    ]
