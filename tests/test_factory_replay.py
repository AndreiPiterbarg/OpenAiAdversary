"""Control-flow doubles; these do not establish a protected runtime capability."""

import hashlib
import json
from types import SimpleNamespace

import pytest

import domains.swe_agents.environment.factory_replay as module
from domains.swe_agents.environment.factory_replay import FactoryArtifactReplay
from domains.swe_agents.environment.protected_oracle import CandidatePatchRejected
from domains.swe_agents.environment.runtime import RuntimeUnavailable


class Session:
    def __init__(self):
        self.stopped = False
        self.commands = []
        self.files = {"tests/test_regression.py": "trusted tests"}
        self.nodes = tuple(
            f"./.prun-factory-abc/test_challenges.py::test_case[{i}]" for i in range(14)
        )

    def exec(self, command, timeout):
        self.commands.append(command)
        if command.startswith("python -I"):
            return 0, json.dumps({"factory/declarations.py": "base"}), ""
        if command == "git rev-parse HEAD":
            return 0, "commit", ""
        if command.startswith("mktemp"):
            return 0, "./.prun-factory-abc", ""
        if "--collect-only" in command:
            return 0, "\n".join(self.nodes), ""
        if command == module.TEST_COMMAND:
            return 0, "\n".join("PASSED " + n for n in module.F2P + module.P2P), ""
        if command.startswith("pytest"):
            return 0, "\n".join("PASSED " + n for n in self.nodes), ""
        return 0, "", ""

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, content):
        self.files[path] = content

    def stop(self):
        self.stopped = True


@pytest.fixture
def replay(monkeypatch):
    verifier = object.__new__(FactoryArtifactReplay)
    verifier.pristine = {"factory/declarations.py": "base"}
    verifier.pin = SimpleNamespace(
        image="image",
        image_sha256="digest",
        url="url",
        commit="commit",
        workdir="workdir",
        python_env="image",
        test_patch="trusted patch",
    )
    verifier.challenges = "trusted challenges"
    verifier.require_execution_boundary = lambda: None
    verifier.record_evidence = None
    verifier.evidence_records = []
    fresh = Session()
    verifier.runtime = SimpleNamespace(start=lambda *a, **kw: fresh)
    checks = []
    verifier.verify_image = lambda *args: checks.append(args)
    monkeypatch.setattr(module, "TEST_SOURCE_SHA256", hashlib.sha256(b"trusted tests").hexdigest())
    monkeypatch.setattr(module, "admit_restricted_sources", lambda *args: {"fixture": True})
    return verifier, fresh, checks


def test_finite_replay_does_not_claim_live_target_isolation(replay):
    verifier, _, _ = replay
    verifier.require_execution_boundary = None
    with pytest.raises(RuntimeUnavailable, match="live target"):
        verifier.require_protected()


def test_export_only_one_file_and_keep_target_alive(replay):
    verifier, fresh, checks = replay
    target = Session()
    target.files["factory/declarations.py"] = "candidate"
    result = verifier.evaluate(target)
    assert fresh.stopped and not target.stopped
    assert len(checks) == 2
    assert result["artifact_replay"]["protected_runtime_attested"] is True
    assert result["artifact_replay"]["full_dual_oracle_evidence"] is False
    assert "installed_packages" not in result
    assert "changed_files" not in result
    assert fresh.files["factory/declarations.py"] == "candidate"
    assert len(result["supplementary_results"]["statuses"]) == 14


def test_invalid_artifact_refused_before_image_or_runtime(replay, monkeypatch):
    verifier, fresh, checks = replay

    def reject(*args):
        raise ValueError("outside grammar")

    monkeypatch.setattr(module, "admit_restricted_sources", reject)
    with pytest.raises(CandidatePatchRejected):
        verifier.evaluate_source("candidate")
    assert not checks and not fresh.commands and not fresh.stopped


def test_source_session_never_stopped_if_runtime_reuses_it(replay):
    verifier, fresh, _ = replay
    with pytest.raises(RuntimeUnavailable, match="distinct fresh"):
        verifier.evaluate_source("candidate", source_session=fresh)
    assert not fresh.stopped


def test_preparation_failure_closes_fresh_session(replay):
    verifier, fresh, _ = replay
    fresh.files["tests/test_regression.py"] = "wrong"
    with pytest.raises(RuntimeUnavailable, match="test source differs"):
        verifier.evaluate_source("candidate")
    assert fresh.stopped


def test_boundary_failure_precedes_candidate_and_image_work(replay):
    verifier, fresh, checks = replay

    def unavailable():
        raise RuntimeUnavailable("boundary attestation failed")

    verifier.require_execution_boundary = unavailable
    with pytest.raises(RuntimeUnavailable, match="attestation failed"):
        verifier.evaluate_source("candidate")
    assert not fresh.commands and not checks


def test_supplementary_collection_and_run_use_identical_root_and_record_before_parse(replay):
    verifier, fresh, _ = replay
    recorded = []
    verifier.record_evidence = recorded.append
    verifier.evaluate_source("candidate")
    supplementary = [x for x in recorded if x["phase"].startswith("supplementary")]
    assert len(supplementary) == 2
    assert all("--rootdir=." in x["command"] for x in supplementary)
    assert [x["phase"] for x in recorded] == [
        "supplementary_collection",
        "frozen_tests",
        "supplementary_tests",
    ]
    assert all("stdout" in x and "stderr" in x and "exit" in x for x in recorded)


def test_actual_pytest_exact_nodes_under_repository_with_inherited_quiet_option(tmp_path):
    import subprocess
    import sys

    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    challenge = tmp_path / ".prun-factory-abc" / "test_challenges.py"
    challenge.parent.mkdir()
    challenge.write_text("def test_case():\n    assert True\n")
    prefix = [
        sys.executable,
        "-m",
        "pytest",
        "--rootdir=.",
        "-o",
        "addopts=",
        "--no-header",
        "-rA",
        "--tb=line",
        "--color=no",
        "-p",
        "no:cacheprovider",
    ]
    relative = str(challenge.relative_to(tmp_path))
    collect = subprocess.run(
        prefix + ["--collect-only", "-q", relative],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    nodes = tuple(x for x in collect.stdout.splitlines() if "test_challenges.py::" in x)
    result = subprocess.run(
        prefix + [relative], cwd=tmp_path, text=True, capture_output=True, check=True
    )
    assert len(nodes) == 1
    assert module.parse_test_results(result.returncode, result.stdout).require(nodes)
