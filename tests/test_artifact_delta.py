"""Real binary capture/replay and fail-closed filesystem boundary regressions."""

import copy
import os
import shutil
import time

import pytest

from domains.swe_agents.environment.artifact_delta import (
    apply_untracked_deltas,
    artifact_digest,
    validate_artifact,
)
from domains.swe_agents.environment.base_rate_replay import (
    capture_candidate_artifact,
    capture_untracked,
)
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from tests import test_base_rate_replay as fixtures
from tests.test_protected_oracle import LocalSession, git


@pytest.fixture
def rig(tmp_path, monkeypatch):
    replay = fixtures.replay.__wrapped__(tmp_path, monkeypatch)
    base = replay.runtime.base
    (base / "old.bin").write_bytes(b"original\x00")
    (base / "delete.dat").write_bytes(b"delete me")
    baseline = capture_untracked(LocalSession(base))
    target = tmp_path / "target"
    shutil.copytree(base, target)
    (target / "old.bin").write_bytes(b"modified\x00\xff")
    (target / "delete.dat").unlink()
    (target / "new_module.py").write_text(
        'raise AssertionError("must not execute during transport")\n'
    )
    (target / "large.bin").write_bytes(bytes(range(256)) * 1024)
    (target / "new_module.py").chmod(0o755)
    (target / "tests/test_candidate.py").write_text("assert False\n")
    artifact = capture_candidate_artifact(
        LocalSession(target), replay.pin.commit, baseline_untracked=baseline
    )
    return replay, artifact, target, tmp_path


def test_binary_roundtrip_new_modified_deleted_and_explicit_test_omission(rig):
    replay, artifact, target, tmp = rig
    fresh = tmp / "fresh"
    shutil.copytree(replay.runtime.base, fresh)
    apply_untracked_deltas(LocalSession(fresh), artifact)
    for name in ("old.bin", "new_module.py", "large.bin"):
        assert (fresh / name).read_bytes() == (target / name).read_bytes()
    assert (fresh / "new_module.py").stat().st_mode & 0o777 == 0o755
    assert not (fresh / "delete.dat").exists()
    assert not (fresh / "tests/test_candidate.py").exists()
    omitted = [x for x in artifact["untracked_deltas"] if x["omission"]]
    assert [x["path"] for x in omitted] == ["tests/test_candidate.py"]
    assert len(artifact["untracked_deltas"]) == 5


def test_data_tampering_and_mode_privilege_rejected(rig):
    _, artifact, _, _ = rig
    for mutation in ("data", "mode", "path"):
        changed = copy.deepcopy(artifact)
        item = next(x for x in changed["untracked_deltas"] if x.get("data_b64"))
        if mutation == "data":
            item["data_b64"] = "AAAA"
        elif mutation == "mode":
            item["after"]["mode"] = 0o4755
        else:
            item["path"] = "../escape.py"
        changed["artifact_sha256"] = artifact_digest(changed)
        with pytest.raises(ValueError):
            validate_artifact(changed)


def test_fresh_baseline_mismatch_prevents_all_writes(rig):
    replay, artifact, _, tmp = rig
    fresh = tmp / "fresh"
    shutil.copytree(replay.runtime.base, fresh)
    (fresh / "old.bin").write_bytes(b"wrong baseline")
    with pytest.raises(RuntimeUnavailable, match="fresh baseline differs"):
        apply_untracked_deltas(LocalSession(fresh), artifact)
    assert (fresh / "delete.dat").exists()
    assert not (fresh / "new_module.py").exists()


@pytest.mark.parametrize("kind", ["fifo", "symlink"])
def test_special_untracked_file_refuses_promptly_and_preserves_patch(tmp_path, monkeypatch, kind):
    replay = fixtures.replay.__wrapped__(tmp_path, monkeypatch)
    base = replay.runtime.base
    if kind == "fifo":
        os.mkfifo(base / "special")
    else:
        (base / "special").symlink_to("/etc/passwd")
    (base / "api.py").write_text("answer = 2\n")
    records = []
    started = time.monotonic()
    with pytest.raises(RuntimeUnavailable):
        capture_candidate_artifact(
            LocalSession(base), replay.pin.commit, record_evidence=records.append
        )
    assert time.monotonic() - started < 5
    assert "+answer = 2" in records[0]["tracked_patch"]
    assert records[0]["capture_error"]


@pytest.mark.parametrize("mutation", ["drop", "before", "after", "omission"])
def test_rehashed_delta_tampering_cannot_change_manifest_binding(rig, mutation):
    _, original, _, _ = rig
    artifact = copy.deepcopy(original)
    item = next(x for x in artifact["untracked_deltas"] if x.get("data_b64"))
    if mutation == "drop":
        artifact["untracked_deltas"].remove(item)
    elif mutation == "before":
        item["before"] = {"sha256": "0" * 64, "size": 0}
    elif mutation == "after":
        item["after"] = {"sha256": "0" * 64, "size": 0}
    else:
        item["omission"] = "new_candidate_test_excluded_from_frozen_code_only_replay"
    artifact["artifact_sha256"] = artifact_digest(artifact)
    with pytest.raises(ValueError):
        validate_artifact(artifact)


def test_existing_untracked_file_promoted_to_git_roundtrips(tmp_path, monkeypatch):
    replay = fixtures.replay.__wrapped__(tmp_path, monkeypatch)
    base = replay.runtime.base
    (base / "module.py").write_text("value = 0\n")
    baseline = capture_untracked(LocalSession(base))
    target = tmp_path / "target"
    shutil.copytree(base, target)
    (target / "module.py").write_text("value = 1\n")
    git(target, "add", "module.py")
    artifact = capture_candidate_artifact(
        LocalSession(target), replay.pin.commit, baseline_untracked=baseline
    )
    fresh = tmp_path / "fresh"
    shutil.copytree(base, fresh)
    apply_untracked_deltas(LocalSession(fresh), artifact)
    patch = tmp_path / "candidate.patch"
    patch.write_text(artifact["tracked_patch"])
    git(fresh, "apply", str(patch))
    assert (fresh / "module.py").read_bytes() == (target / "module.py").read_bytes()


def test_tracked_to_untracked_transition_refuses_without_dropping_evidence(tmp_path, monkeypatch):
    replay = fixtures.replay.__wrapped__(tmp_path, monkeypatch)
    target = tmp_path / "target"
    shutil.copytree(replay.runtime.base, target)
    git(target, "rm", "--cached", "api.py")
    records = []
    artifact = capture_candidate_artifact(
        LocalSession(target), replay.pin.commit, record_evidence=records.append
    )
    fresh = tmp_path / "fresh"
    shutil.copytree(replay.runtime.base, fresh)
    with pytest.raises(RuntimeUnavailable, match="new artifact collides with fresh file"):
        apply_untracked_deltas(LocalSession(fresh), artifact)
    assert "tracked_patch" in records[0]
    assert records[0]["untracked_deltas"][0]["data_b64"]
