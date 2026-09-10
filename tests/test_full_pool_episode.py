"""Prepared checkpoint and honest diagnostic failure recording, no models or jobs."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from domains.swe_agents.scripts import full_pool_episode as episode
from tests.test_domain_swe import pin


class LocalSession:
    def __init__(self, root):
        self.root = root

    def exec(self, command, timeout):
        p = subprocess.run(
            command, shell=True, cwd=self.root, timeout=timeout, capture_output=True, text=True
        )
        return p.returncode, p.stdout, p.stderr

    def write_file(self, path, content):
        Path(path).write_text(content)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def test_checkpoint_includes_new_trusted_test_files(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "source.py").write_text("value = 1\n")
    git(root, "add", "source.py")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "base",
    )
    base = git(root, "rev-parse", "HEAD")
    patch = (
        "diff --git a/test_new.py b/test_new.py\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/test_new.py\n@@ -0,0 +1 @@\n+assert True\n"
    )
    task = pin("k", "r").model_copy(update={"commit": base, "test_patch": patch})
    out = tmp_path / "out"
    out.mkdir()
    prepared = episode.prepare_baseline(LocalSession(root), task, out)
    assert prepared != base
    assert git(root, "show", prepared + ":test_new.py") == "assert True"
    assert git(root, "diff", prepared) == ""
    assert git(root, "show", base + ":source.py") == "value = 1"
    assert json.loads((out / "prepared-baseline.json").read_text())["source_commit"] == base


def test_image_drift_records_unknown_without_start_or_model(tmp_path, monkeypatch, capsys):
    image = tmp_path / "image.sqsh"
    image.write_bytes(b"changed")
    task = pin("k", "r").model_copy(
        update={
            "image": str(image),
            "image_sha256": hashlib.sha256(b"pristine").hexdigest(),
            "workdir": "/repo",
        }
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("must not start a session or spend model calls")

    monkeypatch.setattr(episode.AllocatedRuntime, "start", forbidden)
    monkeypatch.setattr(episode.TrackedRelay, "complete", forbidden)
    result = episode.run_episode(task, tmp_path / "out", "one", verification_mode="diagnostic")
    assert result["status"] == "unknown" and result["failure_stage"] == "image_hash"
    assert result["protected_status"] == "unknown"
    assert result["protected_clean_pass"] is None and result["diagnostic_passed"] is None
    assert result["limits"]["max_steps"] == 100
    assert result["model_calls"] == 0
    assert json.loads(capsys.readouterr().out)["event"] == "episode_complete"


@pytest.mark.parametrize("model", ["gpt-6-astra", "devstral-base-rate"])
def test_only_declared_local_target_identity_is_accepted(tmp_path, model):
    with pytest.raises(ValueError, match="local Devstral"):
        episode.run_episode(
            pin("k", "r"), tmp_path / "out", "one", model, verification_mode="diagnostic"
        )
    assert not (tmp_path / "out").exists()


def test_gold_rehearsal_runs_tools_without_relay_or_claiming_tests(tmp_path, monkeypatch):
    import shlex
    import sys

    from adversary.core.model import CompletionRequest, Message

    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "value.py").write_text("value = 0\n")
    git(root, "add", "value.py")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "base",
    )
    patch = (
        "diff --git a/value.py b/value.py\n--- a/value.py\n+++ b/value.py\n"
        "@@ -1 +1 @@\n-value = 0\n+value = 1\n"
    )
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    model = episode.GoldRehearsal(patch)
    request = CompletionRequest(messages=(Message(role="user", content="rehearse"),))
    first = model.complete(request).message.tool_calls[0]
    argv = shlex.split(first.arguments["command"])
    subprocess.run([sys.executable, *argv[1:]], cwd=root, check=True)
    assert (root / "value.py").read_text() == "value = 1\n"
    second = model.complete(request).message.tool_calls[0]
    assert second.name == "submit" and second.arguments["verified"] is False
    assert model.completed_calls == 2 and model.usage.input_tokens == 0


@pytest.mark.parametrize("gold_passes", [True, False])
def test_candidate_failure_gold_control_is_separate_and_must_pass(tmp_path, gold_passes):
    saved = []

    class Replay:
        record_evidence = staticmethod(saved.append)

        def evaluate_patch(self, patch):
            assert patch == "stored gold"
            self.record_evidence({"gold_raw": True})
            return {
                "test_results": {"exit": 0 if gold_passes else 1},
                "diagnostic_replay": {"statuses": {"test": "PASSED" if gold_passes else "FAILED"}},
            }

    replay = Replay()
    original = replay.record_evidence
    task = pin("k", "r").model_copy(update={"gold_patch": "stored gold"})
    if gold_passes:
        episode.require_guarded_gold(replay, task, tmp_path)
    else:
        with pytest.raises(RuntimeError, match="did not pass"):
            episode.require_guarded_gold(replay, task, tmp_path)
    assert replay.record_evidence is original and not saved
    assert json.loads((tmp_path / "guarded-gold-replay.json").read_text()) == {"gold_raw": True}


@pytest.mark.parametrize("max_steps", [0, -1, True, 1.5])
def test_invalid_step_budget_refuses_before_work(tmp_path, max_steps):
    with pytest.raises(ValueError, match="max_steps"):
        episode.run_episode(pin("k", "r"), tmp_path / "out", "one", max_steps=max_steps)
    assert not (tmp_path / "out").exists()


def test_relay_budget_timeout_preserves_incomplete_call_accounting(tmp_path, monkeypatch, capsys):
    import os
    import time

    from adversary.core.model import CompletionRequest, Message

    read_fd, write_fd = os.pipe()

    class Input:
        def fileno(self):
            return read_fd

    monkeypatch.setattr(episode.sys, "stdin", Input())
    relay = episode.TrackedRelay("test", tmp_path, episode.MODEL, episode.EpisodeBudget())
    deadline = time.perf_counter() + 0.02
    relay.deadline_provider = lambda: deadline
    os.write(write_fd, b'{"error":"interaction_budget_exhausted"}\n')
    try:
        with pytest.raises(TimeoutError):
            relay.complete(CompletionRequest(messages=(Message(role="user", content="issue"),)))
        assert time.perf_counter() >= deadline
        assert relay.calls == 1 and relay.completed_calls == 0
        event = json.loads(capsys.readouterr().out)
        assert event["budget"]["max_steps"] == 100 and event["remaining_seconds"] > 0
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_default_protected_mode_refuses_before_runtime_or_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no runtime or inference allowed")

    monkeypatch.setattr(episode.AllocatedRuntime, "start", forbidden)
    monkeypatch.setattr(episode.TrackedRelay, "complete", forbidden)
    with pytest.raises(episode.RuntimeUnavailable, match="protected verification is unavailable"):
        episode.run_episode(pin("k", "r"), tmp_path / "out", "one")
    assert not (tmp_path / "out").exists()


def test_admission_refusal_is_not_a_test_failure_or_infrastructure_error():
    def refuse():
        raise episode.CandidatePatchRejected("protected input")

    state = episode.evaluate_admission(refuse)
    assert state["admission_status"] == "rejected"
    assert state["diagnostic_passed"] is None
    assert state["diagnostic_replay"]["statuses"] == {}
    assert state["diagnostic_replay"]["protected_status"] == "unknown"
    assert "test_results" not in state
    with pytest.raises(episode.RuntimeUnavailable):
        episode.evaluate_admission(
            lambda: (_ for _ in ()).throw(episode.RuntimeUnavailable("offline"))
        )


@pytest.mark.parametrize(
    "report,expected",
    [
        ({"status": "completed", "diagnostic_passed": True}, (0, 1, 1, 0, 0)),
        ({"status": "completed", "diagnostic_passed": False}, (0, 1, 0, 1, 0)),
        (
            {"status": "completed", "admission_status": "rejected", "diagnostic_passed": None},
            (1, 0, 0, 0, 1),
        ),
        ({"status": "unknown", "diagnostic_passed": None}, (0, 0, 0, 0, 1)),
    ],
)
def test_all_attempts_retained_with_separate_rejection_denominator(report, expected):
    accounting = episode.account_outcome(report)
    assert accounting.pop("attempted") == 1
    assert tuple(accounting.values()) == expected


def test_rejected_artifact_completes_episode_and_retains_trajectory(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from adversary.core.model import Usage

    session = SimpleNamespace(stop=lambda: None, attestation={})
    monkeypatch.setattr(episode, "verify_image", lambda *a: None)
    monkeypatch.setattr(
        episode, "AllocatedRuntime", lambda **k: SimpleNamespace(start=lambda *a, **kw: session)
    )
    monkeypatch.setattr(episode, "prepare_baseline", lambda *a: "0" * 40)
    monkeypatch.setattr(episode, "capture_report_policy", lambda *a: ())
    monkeypatch.setattr(episode, "install_guard", lambda *a: session)
    monkeypatch.setattr(episode, "capture_untracked", lambda *a: {})
    monkeypatch.setattr(episode, "BaseRateReplay", lambda *a, **k: None)

    def reject(*args, **kwargs):
        kwargs["record_evidence"]({"patch": "retained patch", "capture_error": "protected file"})
        raise episode.CandidatePatchRejected("protected file")

    monkeypatch.setattr(episode, "capture_candidate_artifact", reject)
    monkeypatch.setattr(
        episode, "require_guarded_gold", lambda *a: pytest.fail("refusal is not semantic failure")
    )

    class Environment:
        tools = []

        def __init__(self, *args, **kwargs):
            self.final_oracle = kwargs["final_oracle"]

        def run(self, model, budget):
            state = self.final_oracle.evaluate(session)
            return SimpleNamespace(
                final_state=state,
                model_dump=lambda **kw: {"final_state": state},
                steps=0,
                truncated=False,
                stop_reason="submit",
                usage=Usage(),
                claimed_success=False,
            )

    monkeypatch.setattr(episode, "FullPoolEnvironment", Environment)
    task = pin("k", "r").model_copy(
        update={"image": "image", "image_sha256": "0" * 64, "workdir": "/repo"}
    )
    out = tmp_path / "out"
    report = episode.run_episode(task, out, "rejected", verification_mode="diagnostic")
    assert report["status"] == "completed"
    assert report["diagnostic_passed"] is None
    assert report["admission_status"] == "rejected"
    assert report["outcome_accounting"]["attempted"] == 1
    assert report["outcome_accounting"]["admission_rejected"] == 1
    assert report["protected_clean_pass"] is None
    assert (out / "candidate.patch").read_text() == "retained patch"
    assert (out / "trajectory.json").exists()
    assert not (out / "failure.json").exists()


@pytest.mark.parametrize("stop_fails", [False, True])
def test_source_handoff_persists_artifact_state_before_stop(tmp_path, stop_fails):
    import time

    artifact = {"prepared_ref": "a" * 40, "code": "frozen"}
    episode.save(tmp_path / "candidate-artifact.json", artifact)
    episode.save(tmp_path / "tools.json", [{"command": "retained"}])

    class Source:
        attestation = {"guard": "retained"}

        def stop(self):
            state = json.loads((tmp_path / "source-final-state.json").read_text())
            assert state["prepared_ref"] == artifact["prepared_ref"]
            assert "tools.json" in state["retained_receipts"]
            receipt = json.loads((tmp_path / "source-handoff.json").read_text())
            assert receipt["status"] == "stopping"
            if stop_fails:
                raise RuntimeError("stop failed")

    if stop_fails:
        with pytest.raises(RuntimeError, match="stop failed"):
            episode.release_source_for_replay(
                Source(), tmp_path, artifact, episode_started=time.monotonic()
            )
    else:
        episode.release_source_for_replay(
            Source(), tmp_path, artifact, episode_started=time.monotonic()
        )
    receipt = json.loads((tmp_path / "source-handoff.json").read_text())
    assert receipt["status"] == ("failed" if stop_fails else "released")
    if not stop_fails:
        assert receipt["source_stop_completed_seconds"] >= receipt["source_stop_started_seconds"]
    assert (
        receipt["candidate_artifact_sha256"]
        == hashlib.sha256((tmp_path / "candidate-artifact.json").read_bytes()).hexdigest()
    )


def test_handoff_refuses_persisted_artifact_mismatch_before_source_stop(tmp_path):
    episode.save(tmp_path / "candidate-artifact.json", {"prepared_ref": "old"})

    class Source:
        def stop(self):
            raise AssertionError("must retain source if persistence differs")

    with pytest.raises(RuntimeError, match="persisted candidate artifact differs"):
        episode.release_source_for_replay(
            Source(), tmp_path, {"prepared_ref": "new"}, episode_started=0
        )
