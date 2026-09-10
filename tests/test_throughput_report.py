"""Finished-arm denominator and receipt-timing accounting; no runtime calls."""

import json
import os

import pytest

from domains.swe_agents.scripts import throughput_report as report


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def arm(tmp_path):
    tasks = [{"key": str(i), "corpus": "same"} for i in range(5)]
    save(
        tmp_path / "registration.json",
        {
            "config": {
                "tasks": tasks,
                "k": 3,
                "budget": {"max_steps": 100},
                "server_settings": {"eager": False},
            },
            "task_pins": [{"key": str(i), "sha256": str(i) * 64} for i in range(5)],
            "source_manifest_sha256": "a" * 64,
            "owned_step_names": ["step" + str(i) for i in range(5)],
        },
    )
    save(
        tmp_path / "summary.json",
        {"elapsed_seconds_including_stagger_and_cleanup": 3600, "cleanup_verified": True},
    )
    states = [
        {"status": "completed", "episode": {"status": "completed", "diagnostic_passed": True}},
        {"status": "completed", "episode": {"status": "completed", "diagnostic_passed": False}},
        {"status": "completed", "episode": {"status": "completed", "admission_status": "rejected"}},
        {"status": "unknown", "episode": {"status": "unknown"}},
        {"status": "not_attempted"},
    ]
    for i, value in enumerate(states):
        save(tmp_path / "progress" / f"{i}.json", {"key": str(i), **value})
    return tmp_path


def test_denominator_never_drops_refusals_unknown_or_unattempted(tmp_path):
    value = report.load_arm("K3", arm(tmp_path))
    counts = value["counts"]
    assert counts["planned"] == 5 and counts["terminal_attempts"] == 4
    assert counts["tested"] == 2 and counts["unresolved_total"] == 2
    assert counts["not_attempted"] == 1 and counts["without_diagnostic_verdict"] == 3
    assert value["completed_episodes_per_hour"] == 3
    assert value["diagnostic_verdicts_per_hour"] == 2
    assert not value["clean_solve_eligible"]


def test_missing_progress_remains_unknown_and_running_is_refused(tmp_path):
    root = arm(tmp_path)
    (root / "progress/3.json").unlink()
    value = report.load_arm("K3", root)
    assert value["counts"]["unknown"] == value["counts"]["missing_terminal_record"] == 1
    save(root / "progress/3.json", {"key": "3", "status": "running"})
    with pytest.raises(ValueError, match="running"):
        report.load_arm("K3", root)


def test_tokenizer_count_exact_time_proxy_requires_explicit_mtime_attestation(tmp_path):
    before = tmp_path / "call-0001-original-request.json"
    context = tmp_path / "call-0001-context.json"
    save(before, {})
    save(context, {"tokenization_trials": [{}, {}]})
    save(
        tmp_path / "call-0001-completion.json",
        {
            "usage": {"wall_seconds": 2},
            "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 4}},
        },
    )
    os.utime(before, (100, 100))
    os.utime(context, (103, 103))
    value = report.call_metrics(tmp_path, native_mtimes=False)
    assert value["recorded_tokenizer_trials"] == 2
    assert value["tokenizer_http_seconds"] is value["context_projection_receipt_seconds"] is None
    assert value["measured_input_tokens"] == 10 and value["measured_output_tokens"] == 4
    assert (
        report.call_metrics(tmp_path, native_mtimes=True)["context_projection_receipt_seconds"][
            "sum"
        ]
        == 3
    )


def test_matched_task_check_uses_pin_hash_not_only_task_names(tmp_path):
    first = report.load_arm("K3", arm(tmp_path / "a"))
    second = report.load_arm("K6", arm(tmp_path / "b"))
    second["pin_bindings"]["0"] = "changed"
    comparison = report.compare([first, second])
    assert not comparison["same_registered_task_pins"] and comparison["matched_task_count"] == 4
    assert "not randomized" in comparison["caveat"]
