"""Real Git transport checks; guarded invocation doubles do not prove protection."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import domains.swe_agents.environment.base_rate_replay as module
from domains.swe_agents.environment.base_rate_replay import BaseRateReplay, export_prepared_patch
from domains.swe_agents.environment.protected_oracle import CandidatePatchRejected
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from tests import test_protected_oracle as fixtures
from tests.test_protected_oracle import LocalSession, git, patch_for


@pytest.fixture
def replay(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    return fixtures.replay.__wrapped__(tmp_path)


def test_export_includes_committed_edits_and_new_tracked_files(replay):
    base = replay.runtime.base
    (base / "api.py").write_text("answer = 1\n")
    (base / "new.py").write_text("added = True\n")
    git(base, "add", "api.py", "new.py")
    git(base, "commit", "-qm", "candidate change")
    patch = export_prepared_patch(LocalSession(base), replay.pin.commit)
    assert "+answer = 1" in patch
    assert "+added = True" in patch


def test_export_refuses_untracked_including_ignored_files(replay):
    base = replay.runtime.base
    (base / ".gitignore").write_text("ignored.py\n")
    git(base, "add", ".gitignore")
    git(base, "commit", "-qm", "ignore config")
    (base / "ignored.py").write_text("hidden = True\n")
    with pytest.raises(CandidatePatchRejected, match="untracked"):
        export_prepared_patch(LocalSession(base), replay.pin.commit)


@pytest.fixture
def diagnostic(replay, monkeypatch):
    calls = []

    def guard(session, repo, **kwargs):
        scratch = session.root / ".guard-scratch"
        scratch.mkdir()

        def execute(command, timeout):
            calls.append(command)
            if command == replay.pin.test_command:
                return 0, "PASSED tests/test_api.py::test_answer\n", ""
            return session.exec(command, timeout)

        return SimpleNamespace(
            exec=execute, scratch=str(scratch), attestation={"fixture_only": True}
        )

    monkeypatch.setattr(module, "install_guard", guard)
    checked = []
    oracle = BaseRateReplay(
        replay.runtime,
        replay.pin,
        prepared_ref=replay.pin.commit,
        verify_image=lambda *args: checked.append(args),
    )
    return oracle, calls, checked


def test_candidate_tests_only_use_guarded_invocation(diagnostic, replay):
    oracle, calls, checked = diagnostic
    result = oracle.evaluate_patch(patch_for(replay, "api.py", "answer = 1\n"))
    assert calls[-1] == replay.pin.test_command
    assert any(command.startswith("git apply --check") for command in calls)
    assert any(command.startswith("git apply -- ") for command in calls)
    assert replay.pin.test_command not in replay.runtime.sessions[-1].commands
    assert replay.runtime.sessions[-1].closed
    assert len(checked) == 2
    assert result["diagnostic_replay"]["protected_status"] == "unknown"
    assert "installed_packages" not in result and "changed_files" not in result
    with pytest.raises(RuntimeUnavailable, match="unknown"):
        oracle.require_protected()


def test_protected_patch_rejected_before_candidate_execution(diagnostic, replay):
    oracle, calls, _ = diagnostic
    with pytest.raises(CandidatePatchRejected, match="protected input"):
        oracle.evaluate_patch(patch_for(replay, "tests/test_api.py", "assert False\n"))
    assert replay.pin.test_command not in calls
    assert replay.runtime.sessions[-1].closed


def test_raw_evidence_retained_before_incomplete_status_refusal(diagnostic, monkeypatch):
    oracle, _, _ = diagnostic
    monkeypatch.setattr(
        module,
        "install_guard",
        lambda *args, **kwargs: SimpleNamespace(
            exec=lambda *a: (0, "no required test statuses", ""), attestation={}
        ),
    )
    with pytest.raises(ValueError, match="missing"):
        oracle.evaluate_patch("")
    assert oracle.evidence_records[0]["stdout"] == "no required test statuses"


def test_unchanged_preexisting_untracked_allowed_but_changes_rejected(replay):
    base = replay.runtime.base
    artifact = base / "existing.dat"
    artifact.write_bytes(b"pristine")
    session = LocalSession(base)
    before = module.capture_untracked(session)
    assert before["existing.dat"]["size"] == 8
    assert export_prepared_patch(session, replay.pin.commit, baseline_untracked=before) == ""
    artifact.write_bytes(b"modified")
    with pytest.raises(CandidatePatchRejected, match="changed"):
        export_prepared_patch(session, replay.pin.commit, baseline_untracked=before)


def test_full_parameter_identifiers_preserved(diagnostic, monkeypatch):
    oracle, _, _ = diagnostic
    node = "tests/test_api.py::test_answer[with space - parameter]"
    oracle.pin = oracle.pin.model_copy(update={"fail_to_pass": (node,)})
    monkeypatch.setattr(
        module,
        "install_guard",
        lambda *a, **k: SimpleNamespace(
            exec=lambda *a: (0, "PASSED " + node + "\n", ""), attestation={}
        ),
    )
    result = oracle.evaluate_patch("")
    assert set(result["diagnostic_replay"]["statuses"]) == {node}


def test_declared_reports_only_from_frozen_addopts():
    assert module.declared_report_paths(
        {
            "setup.cfg": "[tool:pytest]\naddopts = --junitxml=pytest.xml --cov=pyls --cov-report=xml\n",
        }
    ) == (".coverage", "coverage.xml", "pytest.xml")
    assert (
        module.declared_report_paths(
            {
                "pytest.ini": "[pytest]\naddopts = -q\n",
                "setup.cfg": "[tool:pytest]\naddopts = --junitxml=pytest.xml\n",
            }
        )
        == ()
    )
    assert (
        module.declared_report_paths(
            {
                "pytest.ini": "[pytest]\naddopts = --junitxml=source.py\n",
            }
        )
        == ()
    )


def test_generated_report_omission_audited_and_source_not_exempted(replay):
    base = replay.runtime.base
    session = LocalSession(base)
    (base / "pytest.xml").write_text("<testsuites/>")
    records = []
    patch = export_prepared_patch(
        session,
        replay.pin.commit,
        generated_report_paths=("pytest.xml",),
        record_evidence=records.append,
    )
    assert patch == ""
    assert records[-1]["omitted_generated_reports"]["pytest.xml"]["after"]["size"] == 13
    (base / "new_source.py").write_text("answer = 1\n")
    (base / "api.py").write_text("answer = 2\n")
    with pytest.raises(CandidatePatchRejected):
        export_prepared_patch(
            session,
            replay.pin.commit,
            generated_report_paths=("pytest.xml",),
            record_evidence=records.append,
        )
    assert "+answer = 2" in records[-1]["patch"]
    assert "new_source.py" in records[-1]["current_untracked"]


def test_undeclared_report_still_refused(replay):
    (replay.runtime.base / "pytest.xml").write_text("<testsuites/>")
    with pytest.raises(CandidatePatchRejected):
        export_prepared_patch(LocalSession(replay.runtime.base), replay.pin.commit)


def test_declared_html_report_is_narrow_not_source_exemption(replay):
    assert module.declared_report_paths(
        {"pytest.ini": "[pytest]\naddopts=--cov-report html\n"}
    ) == ("htmlcov/",)
    base = replay.runtime.base
    (base / "htmlcov").mkdir()
    (base / "htmlcov/index.html").write_text("report")
    records = []
    assert (
        export_prepared_patch(
            LocalSession(base),
            replay.pin.commit,
            generated_report_paths=("htmlcov/",),
            record_evidence=records.append,
        )
        == ""
    )
    assert "htmlcov/index.html" in records[-1]["omitted_generated_reports"]
    (base / "htmlcov/evil.py").write_text("arbitrary = True")
    with pytest.raises(CandidatePatchRejected):
        export_prepared_patch(
            LocalSession(base), replay.pin.commit, generated_report_paths=("htmlcov/",)
        )


def test_required_postcheck_failure_overrides_frozen_pass(diagnostic, monkeypatch):
    oracle, calls, _ = diagnostic
    stages = []

    class PostCheck:
        def evaluate(self, guarded, frozen, **kwargs):
            stages.append("post_evaluate")
            assert frozen[0] == 0
            return {
                "diagnostic_passed": False,
                "post_checks": {"required": True},
                "supplementary_results": {"exit": 1},
            }

    def prepare(pin, session, **kwargs):
        stages.append("trusted_prepare")
        assert not calls
        return PostCheck()

    monkeypatch.setattr(module, "prepare_task_post_check", prepare)
    result = oracle.evaluate_patch("")
    assert result["diagnostic_passed"] is False
    assert result["post_checks"]["required"]
    assert stages == ["trusted_prepare", "post_evaluate"]


def test_final_timeout_with_complete_pass_lines_remains_unknown(diagnostic, monkeypatch):
    oracle, _, _ = diagnostic
    original = module.install_guard

    def guard(*args, **kwargs):
        session = original(*args, **kwargs)
        execute = session.exec
        session.exec = lambda command, timeout: (
            (124, "PASSED tests/test_api.py::test_answer\n", "timeout")
            if command == oracle.pin.test_command
            else execute(command, timeout)
        )
        return session

    monkeypatch.setattr(module, "install_guard", guard)
    with pytest.raises(RuntimeUnavailable, match="timed out"):
        oracle.evaluate_patch("")
    assert oracle.evidence_records[-1]["exit"] == 124


def test_handoff_releases_source_before_distinct_fresh_session(diagnostic, replay, monkeypatch):
    oracle, _, _ = diagnostic
    events = []

    class Source(LocalSession):
        def exec(self, command, timeout):
            assert not self.closed, "source accessed after handoff"
            return super().exec(command, timeout)

        def stop(self):
            events.append("source.stop")
            super().stop()

    source = Source(replay.runtime.base)
    artifact = module.capture_candidate_artifact(source, replay.pin.commit)
    start = oracle.runtime.start

    def fresh(*args, **kwargs):
        assert source.closed
        events.append("fresh.start")
        return start(*args, **kwargs)

    monkeypatch.setattr(oracle.runtime, "start", fresh)
    result = oracle.evaluate_artifact(artifact, source_session=source, release_source=source.stop)
    assert events == ["source.stop", "fresh.start"]
    assert result["test_results"]["exit"] == 0
    assert result["diagnostic_replay"]["untracked_artifact"] == artifact
    assert oracle.runtime.sessions[-1].closed


def test_unbound_artifact_never_releases_source_or_starts_verifier(diagnostic, replay, monkeypatch):
    oracle, _, _ = diagnostic
    source = LocalSession(replay.runtime.base)
    artifact = module.capture_candidate_artifact(source, replay.pin.commit)
    artifact["prepared_ref"] = "0" * 40

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid artifact must retain source and never start replay")

    monkeypatch.setattr(oracle.runtime, "start", forbidden)
    with pytest.raises(CandidatePatchRejected):
        oracle.evaluate_artifact(artifact, source_session=source, release_source=forbidden)
    assert not source.closed


def test_source_stop_failure_prevents_fresh_start(diagnostic, replay, monkeypatch):
    oracle, _, _ = diagnostic
    source = LocalSession(replay.runtime.base)
    artifact = module.capture_candidate_artifact(source, replay.pin.commit)

    def failed_stop():
        raise RuntimeError("source did not stop")

    def forbidden(*args, **kwargs):
        raise AssertionError("fresh replay would overlap source")

    monkeypatch.setattr(oracle.runtime, "start", forbidden)
    with pytest.raises(RuntimeError, match="source did not stop"):
        oracle.evaluate_artifact(artifact, source_session=source, release_source=failed_stop)
