"""Host transport diagnostics; local doubles do not attest the Linux boundary."""

from types import SimpleNamespace

import pytest

from domains.swe_agents.environment import interactive_replay as module
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from tests import test_protected_oracle as fixtures
from tests.test_protected_oracle import LocalSession, patch_for


@pytest.fixture
def host(tmp_path, monkeypatch):
    pristine = fixtures.replay.__wrapped__(tmp_path)
    runtime = pristine.runtime
    runtime.pin = SimpleNamespace(kind="interactive_host_runtime_v1",
                                  repository_sha256="a" * 64, venv_sha256="b" * 64)
    runtime.verify = lambda: None
    runtime.start_guarded = lambda boundary: boundary(runtime.start(), runtime.pin)
    calls = []

    def guard(raw, pin, **kwargs):
        scratch = raw.root / "scratch"
        scratch.mkdir()

        def execute(command, timeout):
            calls.append(command)
            if command == pristine.pin.test_command:
                return 0, "PASSED tests/test_api.py::test_answer\n", ""
            return raw.exec(command, timeout)

        return SimpleNamespace(exec=execute, stop=raw.stop, scratch=str(scratch),
                               attestation={"fixture": True}, command_timeout=60)

    monkeypatch.setattr(module, "install_host_guard", guard)
    replay = module.HostReplay(runtime, pristine.pin, host_nproc=128,
                               prepared_ref=pristine.pin.commit)
    return replay, pristine, calls


def test_host_replay_confines_candidate_git_and_retains_unknown(host):
    replay, pristine, calls = host
    result = replay.evaluate_patch(patch_for(pristine, "api.py", "answer = 1\n"))
    assert any(command.startswith("git apply --check") for command in calls)
    assert result["diagnostic_passed"] is True
    receipt = result["diagnostic_replay"]
    assert receipt["protected_status"] == "unknown"
    assert receipt["kind"] == "diagnostic_host_test_replay"
    assert "image_sha256" not in receipt
    assert receipt["venv_sha256"] == "b" * 64
    assert pristine.runtime.sessions[-1].closed
    with pytest.raises(RuntimeUnavailable, match="unknown"):
        replay.require_protected()


def test_host_replay_requires_source_release(host):
    replay, pristine, _ = host
    source = LocalSession(pristine.runtime.base)
    with pytest.raises(RuntimeUnavailable, match="source release"):
        replay.evaluate_patch("", source_session=source)
    assert not pristine.runtime.sessions


def test_host_source_stop_failure_never_allocates_fresh(host):
    replay, pristine, _ = host

    def broken():
        raise RuntimeError("stop failed")

    with pytest.raises(RuntimeError, match="stop failed"):
        replay.evaluate_patch("", source_session=LocalSession(pristine.runtime.base),
                              release_source=broken)
    assert not pristine.runtime.sessions


def test_host_supplementary_failure_cannot_be_hidden(host, monkeypatch):
    replay, _, _ = host
    monkeypatch.setattr(module, "prepare_task_post_check", lambda *a, **k: SimpleNamespace(
        evaluate=lambda *a, **k: {"diagnostic_passed": False, "required_postcheck": True}
    ))
    result = replay.evaluate_patch("")
    assert result["diagnostic_passed"] is False and result["required_postcheck"]
