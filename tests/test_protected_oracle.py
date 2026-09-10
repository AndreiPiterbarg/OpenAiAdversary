"""Fresh replay diagnostics exercised with real local Git; no cluster or model calls."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from adversary.core.trajectory import Budget
from domains.swe_agents.environment.environment import SweEnvironment
from domains.swe_agents.environment.protected_oracle import (
    CandidatePatchRejected,
    FreshReplayOracle,
)
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from domains.swe_agents.environment.spec import SweOracle, SweTaskSpec, TaskPin


class LocalSession:
    def __init__(self, root: Path) -> None:
        self.root, self.closed = root, False
        self.commands: list[str] = []
        self.written: list[Path] = []

    def exec(self, command: str, timeout: float) -> tuple[int, str, str]:
        self.commands.append(command)
        result = subprocess.run(
            command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr

    def write_file(self, path: str, content: str) -> None:
        Path(path).write_text(content)
        self.written.append(Path(path))

    def read_file(self, path: str) -> str:
        return (self.root / path).read_text()

    def checkpoint(self) -> None:
        pass

    def snapshot(self) -> dict[str, Any]:
        return {"changed_files": [], "installed_packages": {}, "added_packages": []}

    def stop(self) -> None:
        self.closed = True
        for path in self.written:
            path.unlink(missing_ok=True)


class LocalRuntime:
    def __init__(self, base: Path, destination: Path) -> None:
        self.base, self.destination = base, destination
        self.sessions: list[LocalSession] = []

    def start(self, *args: Any, **kwargs: Any) -> LocalSession:
        root = self.destination / str(len(self.sessions))
        shutil.copytree(self.base, root)
        session = LocalSession(root)
        self.sessions.append(session)
        return session


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True)


@pytest.fixture
def replay(tmp_path: Path) -> FreshReplayOracle:
    base = tmp_path / "base"
    base.mkdir()
    git(base, "init", "-q")
    git(base, "config", "user.email", "fixture@example.invalid")
    git(base, "config", "user.name", "Fixture")
    (base / "api.py").write_text("answer = 0\n")
    (base / "tests").mkdir()
    (base / "tests/test_api.py").write_text("assert True\n")
    (base / "pyproject.toml").write_text("# original\n")
    git(base, "add", ".")
    git(base, "commit", "-qm", "base")
    image = tmp_path / "image.sqsh"
    image.write_bytes(b"fixture image")
    command = f"{sys.executable} -c 'import api; assert api.answer == 1'"
    pin = TaskPin(
        key="fixture", repo="fixture", url="https://example.invalid/fixture",
        commit=git(base, "rev-parse", "HEAD").strip(), issue="Fix answer", properties={},
        test_command=command, fail_to_pass=("tests/test_api.py::test_answer",),
        image=str(image), image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
    )
    oracle = SweOracle(test_command=command, fail_to_pass=pin.fail_to_pass, canary="fixture")
    return FreshReplayOracle(LocalRuntime(base, tmp_path / "sessions"), pin, oracle)


def patch_for(replay: FreshReplayOracle, path: str, contents: str) -> str:
    base = replay.runtime.base
    (base / path).write_text(contents)
    patch = git(base, "diff", "--binary")
    git(base, "checkout", "--", path)
    return patch


def test_replay_uses_fresh_state_and_candidate_only(replay: FreshReplayOracle) -> None:
    patch = patch_for(replay, "api.py", "answer = 1\n")
    state = replay.evaluate_patch(patch)
    assert state["test_results"]["exit"] == 0
    assert state["oracle_replay"]["kind"] == "fresh_replay_unisolated"
    assert state["oracle_replay"]["changed_paths"] == ["api.py"]
    assert replay.runtime.sessions[0].closed
    assert (replay.runtime.base / "api.py").read_text() == "answer = 0\n"


def test_candidate_test_failure_is_evidence_not_infrastructure(replay: FreshReplayOracle) -> None:
    state = replay.evaluate_patch("")
    assert state["test_results"]["exit"] == 1
    assert replay.runtime.sessions[0].closed


@pytest.mark.parametrize("path", ["tests/test_api.py", "pyproject.toml"])
def test_test_and_configuration_tampering_rejected(replay: FreshReplayOracle, path: str) -> None:
    patch = patch_for(replay, path, "# tampered\n")
    with pytest.raises(CandidatePatchRejected, match="verifier input"):
        replay.evaluate_patch(patch)
    assert replay.runtime.sessions[0].closed
    assert replay.pin.test_command not in replay.runtime.sessions[0].commands


@pytest.mark.parametrize("patch", ["not a patch", "\x00", "a" * (4 * 1024 * 1024 + 1), "\ud800"], ids=["invalid", "nul", "oversized", "non-utf8"])
def test_malformed_and_bounded_transport(replay: FreshReplayOracle, patch: str) -> None:
    with pytest.raises(CandidatePatchRejected):
        replay.evaluate_patch(patch)
    assert all(s.closed for s in replay.runtime.sessions)


def test_unsafe_path_refused(replay: FreshReplayOracle) -> None:
    patch = patch_for(replay, "api.py", "answer = 1\n")
    patch = patch.replace("a/api.py", "a/../escape.py").replace("b/api.py", "b/../escape.py")
    with pytest.raises(CandidatePatchRejected):
        replay.evaluate_patch(patch)
    assert all(s.closed for s in replay.runtime.sessions)


def test_image_drift_refused_before_start(replay: FreshReplayOracle) -> None:
    Path(replay.pin.image).write_bytes(b"wrong image")
    with pytest.raises(RuntimeUnavailable, match="digest"):
        replay.evaluate_patch("")
    assert not replay.runtime.sessions


def test_unapplicable_patch_refused_and_cleaned(replay: FreshReplayOracle) -> None:
    patch = patch_for(replay, "api.py", "answer = 1\n").replace("-answer = 0", "-answer = 9")
    with pytest.raises(CandidatePatchRejected, match="does not apply"):
        replay.evaluate_patch(patch)
    assert replay.runtime.sessions[0].closed


def test_trusted_test_patch_setup_failure_is_infrastructure(replay: FreshReplayOracle) -> None:
    replay.pin = replay.pin.model_copy(update={"test_patch": "not a patch"})
    with pytest.raises(RuntimeUnavailable, match="setup failed"):
        replay.evaluate_patch("")
    assert replay.runtime.sessions[0].closed


def test_requires_explicit_baseline_exporter(replay: FreshReplayOracle) -> None:
    with pytest.raises(RuntimeUnavailable, match="exporter"):
        replay.evaluate(LocalSession(replay.runtime.base))
    assert not replay.runtime.sessions


def test_protection_refused_before_model_call(replay: FreshReplayOracle) -> None:
    environment = SweEnvironment(
        "fixture", SweTaskSpec(pin=replay.pin, canary="fixture"), replay.oracle,
        LocalSession(replay.runtime.base), final_oracle=replay, require_protected_oracle=True,
    )
    with pytest.raises(RuntimeUnavailable, match="not a protected oracle"):
        environment.run(None, Budget(max_steps=1))
    assert not replay.runtime.sessions


def test_missing_protected_oracle_refused_before_model_call(replay: FreshReplayOracle) -> None:
    environment = SweEnvironment(
        "fixture", SweTaskSpec(pin=replay.pin, canary="fixture"), replay.oracle,
        LocalSession(replay.runtime.base), require_protected_oracle=True,
    )
    with pytest.raises(RuntimeUnavailable, match="no model call"):
        environment.run(None, Budget(max_steps=1))


def test_environment_uses_oracle_callback(replay: FreshReplayOracle) -> None:
    patch = patch_for(replay, "api.py", "answer = 1\n")
    replay.export_patch = lambda _: patch
    environment = SweEnvironment(
        "fixture", SweTaskSpec(pin=replay.pin, canary="fixture"), replay.oracle,
        LocalSession(replay.runtime.base), final_oracle=replay,
    )
    assert environment._final_state()["test_results"]["exit"] == 0


def test_trusted_tests_are_restored_in_fresh_replay(replay: FreshReplayOracle) -> None:
    trusted_patch = patch_for(replay, "tests/test_api.py", "# trusted evaluator revision\n")
    replay.pin = replay.pin.model_copy(update={"test_patch": trusted_patch})
    candidate = patch_for(replay, "api.py", "answer = 1\n")
    replay.evaluate_patch(candidate)
    fresh = replay.runtime.sessions[0]
    assert (fresh.root / "tests/test_api.py").read_text() == "# trusted evaluator revision\n"
    assert fresh.closed


def test_runtime_reusing_target_is_refused_without_closing_target(
    replay: FreshReplayOracle, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = LocalSession(replay.runtime.base)
    monkeypatch.setattr(replay.runtime, "start", lambda *args, **kwargs: source)
    with pytest.raises(RuntimeUnavailable, match="distinct fresh session"):
        replay.evaluate_patch("", source_session=source)
    assert not source.closed and not source.commands


def test_test_transport_failure_always_closes_session(
    replay: FreshReplayOracle, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalSession.exec

    def failed_exec(self: LocalSession, command: str, timeout: float) -> tuple[int, str, str]:
        if command == replay.pin.test_command:
            raise RuntimeUnavailable("test transport disconnected")
        return original(self, command, timeout)

    monkeypatch.setattr(LocalSession, "exec", failed_exec)
    with pytest.raises(RuntimeUnavailable, match="disconnected"):
        replay.evaluate_patch("")
    assert replay.runtime.sessions[0].closed
