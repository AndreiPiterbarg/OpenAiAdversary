"""Public export keeps registered missing runs and separates calibration."""

import json

import pytest

from domains.swe_agents.scripts.interactive_results import export_results


def test_partial_calibration_keeps_all_registered_denominators(tmp_path):
    root = tmp_path / "calibration"
    root.mkdir()
    runs = [dict(id=f"run-{i}", task_index=0, repetition=i, seed=9000+i) for i in range(5)]
    (root / "registration.json").write_text(json.dumps({
        "kind": "calibration", "runs": runs, "never_pool_with_perturbation_arm": True,
    }))
    for i in range(5):
        directory = root / f"run-{i}"
        directory.mkdir()
        (directory / "metadata.json").write_text(json.dumps({"task_key": "task"}))
        if i < 2:
            (directory / "episode.json").write_text(json.dumps({
                "task_key": "task", "status": "completed", "diagnostic_passed": True,
            }))
    report = export_results(root, tmp_path / "public.json")
    assert report["arm_kind"] == "calibration_only"
    assert report["summary"]["planned"] == 5
    assert report["summary"]["diagnostic_measured"] == 2
    assert report["summary"]["unknown"] == report["pending_or_missing"] == 3
    assert report["summary"]["groups"][0]["task_failure"] is None
    assert report["summary"]["contrasts"] == []
    assert "registration.json" in report["evidence_sha256"]


def test_export_refuses_assignment_drift(tmp_path):
    run = dict(id="one", task={"key": "task"}, cell_index=1, repetition=0, seed=7)
    (tmp_path / "registration.json").write_text(json.dumps({"runs": [run]}))
    (tmp_path / "one").mkdir()
    (tmp_path / "one/result.json").write_text(json.dumps({**run, "seed": 8}))
    with pytest.raises(ValueError, match="assignment"):
        export_results(tmp_path, tmp_path / "public.json")


def test_sharded_export_binds_assignments_and_keeps_missing_cells(tmp_path):
    from domains.swe_agents.scripts.interactive_astra_batch import shard_registration

    task = {"key": "task"}
    runs = [dict(id=f"task-0-cell-{c}-rep-{r}", task=task, cell_index=c,
                 repetition=r, seed=7+r) for r in range(5) for c in range(4)]
    manifest = {"tasks": [task], "runs": runs}
    (tmp_path / "registration.json").write_text(json.dumps(manifest))
    directory = tmp_path / "shards" / "task-0-cell-0"
    directory.mkdir(parents=True)
    shard = shard_registration(manifest, 0, 0)
    (directory / "registration.json").write_text(json.dumps(shard))
    run = shard["runs"][0]
    (directory / run["id"]).mkdir()
    (directory / run["id"] / "result.json").write_text(json.dumps({
        **run, "diagnostic_passed": True, "status": "completed",
    }))
    report = export_results(tmp_path, tmp_path / "public.json")
    assert report["terminal_receipts"] == 1
    assert report["summary"]["planned"] == 20
    assert report["summary"]["unknown"] == report["pending_or_missing"] == 19
    assert report["summary"]["diagnostic_passes"] == 1
    assert report["rows"][0]["id"] == run["id"]
    assert "shards/task-0-cell-0/registration.json" in report["evidence_sha256"]
    shard["runs"][0]["seed"] += 1
    (directory / "registration.json").write_text(json.dumps(shard))
    with pytest.raises(ValueError, match="shard assignment"):
        export_results(tmp_path, tmp_path / "public.json")


def test_sharded_export_refuses_duplicate_membership(tmp_path):
    import hashlib

    run = dict(id="one", task={"key": "task"}, cell_index=0, repetition=0, seed=7)
    manifest = {"runs": [run]}
    (tmp_path / "registration.json").write_text(json.dumps(manifest))
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    for name in ("a", "b"):
        directory = tmp_path / "shards" / name
        directory.mkdir(parents=True)
        (directory / "registration.json").write_text(json.dumps({
            "canonical_manifest_sha256": digest, "runs": [run],
        }))
    with pytest.raises(ValueError, match="duplicate shard"):
        export_results(tmp_path, tmp_path / "public.json")
