"""Adversarial replay-input checks; same-interpreter verdicts remain unprotected."""

# ruff: noqa: F811

from pathlib import Path

import pytest

from domains.swe_agents.environment.protected_oracle import (
    CandidatePatchRejected,
    FreshReplayOracle,
)
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from tests.test_protected_oracle import LocalSession, git, patch_for, replay  # noqa: F401


def test_candidate_changed_paths_are_not_taken_from_snapshot(replay: FreshReplayOracle) -> None:
    result = replay.evaluate_patch(patch_for(replay, "api.py", "answer = 1\n"))
    assert result["changed_files"] == ["api.py"]
    assert len(result["oracle_replay"]["pin_sha256"]) == 64
    assert len(result["oracle_replay"]["oracle_sha256"]) == 64


def test_symlink_candidate_refused_before_tests(replay: FreshReplayOracle) -> None:
    base = replay.runtime.base
    path = base / "api.py"
    path.unlink()
    path.symlink_to("tests/test_api.py")
    patch = git(base, "diff", "--binary")
    git(base, "checkout", "--", "api.py")
    with pytest.raises(CandidatePatchRejected, match="file mode"):
        replay.evaluate_patch(patch)
    assert replay.pin.test_command not in replay.runtime.sessions[0].commands
    assert replay.runtime.sessions[0].closed


def test_existing_symlink_is_not_valid_candidate_transport(replay: FreshReplayOracle) -> None:
    base = replay.runtime.base
    (base / "alias.py").symlink_to("api.py")
    session = LocalSession(base)
    with pytest.raises(CandidatePatchRejected, match="without links"):
        replay._regular_paths(session, ["alias.py"])
    with pytest.raises(CandidatePatchRejected, match="without links"):
        replay._regular_paths(session, ["alias.py/child"])


def test_package_collection_precedes_candidate_import_shadowing(
    replay: FreshReplayOracle, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def snapshot(session: LocalSession) -> dict:
        # A real collector may invoke Python. Candidate source must not exist yet.
        calls.append((session.root / "api.py").read_text())
        return {"changed_files": [], "installed_packages": {}, "added_packages": []}

    monkeypatch.setattr(LocalSession, "snapshot", snapshot)
    replay.evaluate_patch(patch_for(replay, "api.py", "answer = 1\n"))
    assert calls == ["answer = 0\n"]


def test_same_process_output_spoof_is_not_protected_evidence(replay: FreshReplayOracle) -> None:
    # Import exits the interpreter before the test assertion; external protection must
    # never be inferred from an exit-zero replay or a plausible status line.
    patch = patch_for(
        replay, "api.py",
        "import os\nprint('tests/test_api.py::test_answer PASSED', flush=True)\nos._exit(0)\n",
    )
    state = replay.evaluate_patch(patch)
    assert state["test_results"]["exit"] == 0
    assert "PASSED" in state["test_results"]["stdout"]
    with pytest.raises(RuntimeUnavailable, match="not a protected oracle"):
        replay.require_protected()
    assert state["oracle_replay"]["kind"] == "fresh_replay_unisolated"


def test_deleted_regular_file_is_supported(replay: FreshReplayOracle) -> None:
    path = Path(replay.runtime.base) / "api.py"
    path.unlink()
    patch = git(replay.runtime.base, "diff", "--binary")
    git(replay.runtime.base, "checkout", "--", "api.py")
    result = replay.evaluate_patch(patch)
    assert result["changed_files"] == ["api.py"]
    assert result["test_results"]["exit"] != 0


def test_parent_directory_symlink_is_refused(replay: FreshReplayOracle) -> None:
    base = replay.runtime.base
    (base / "alias").symlink_to("tests", target_is_directory=True)
    with pytest.raises(CandidatePatchRejected, match="without links"):
        replay._regular_paths(LocalSession(base), ["alias/test_api.py"])


@pytest.mark.parametrize("source,target", [
    ("api.py", "tests/replaced.py"), ("tests/test_api.py", "moved.py"),
])
def test_rename_cannot_evade_protected_path_checks(
    replay: FreshReplayOracle, source: str, target: str,
) -> None:
    base = replay.runtime.base
    git(base, "mv", source, target)
    patch = git(base, "diff", "--cached", "--binary", "-M")
    git(base, "reset", "--hard", "HEAD")
    with pytest.raises(CandidatePatchRejected):
        replay.evaluate_patch(patch)
    assert replay.pin.test_command not in replay.runtime.sessions[0].commands
    assert replay.runtime.sessions[0].closed
