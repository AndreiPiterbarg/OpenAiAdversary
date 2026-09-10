"""Fresh host diagnostic replay with the same bounded code-artifact admission."""

from __future__ import annotations

import hashlib
import shlex
from collections.abc import Callable
from typing import Any

from adversary.domain.channel import relative_path
from domains.swe_agents.environment.artifact_delta import apply_untracked_deltas
from domains.swe_agents.environment.base_rate_replay import BaseRateReplay, _checked
from domains.swe_agents.environment.factory_postcheck import prepare_task_post_check
from domains.swe_agents.environment.guarded_session import install_host_guard
from domains.swe_agents.environment.protected_oracle import CandidatePatchRejected
from domains.swe_agents.environment.prun_contract import parse_pytest_summary
from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session
from domains.swe_agents.environment.test_results import TestEvidence, TestStatus


class HostReplay(BaseRateReplay):
    """Pristine host repository already contains its pinned trusted test patch."""

    def __init__(self, runtime: Any, pin: Any, *, host_nproc: int,
                 prepared_ref: str, **kwargs: Any) -> None:
        self.host_nproc = host_nproc
        super().__init__(runtime, pin, prepared_ref=prepared_ref,
                         verify_image=lambda *_: runtime.verify(), **kwargs)

    def evaluate_patch(
        self, patch: str, *, source_session: Session | None = None,
        untracked_artifact: dict[str, Any] | None = None,
        release_source: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        encoded = self._validate_patch_transport(patch, untracked_artifact)
        self.runtime.verify()
        if source_session is not None:
            if release_source is None:
                raise RuntimeUnavailable("host replay requires confirmed source release")
            release_source()
        elif release_source is not None:
            raise RuntimeUnavailable("source release requires source identity")
        prepared: dict[str, Any] = {}

        def boundary(raw: Any, runtime_pin: Any) -> Any:
            if raw is source_session:
                raise RuntimeUnavailable("host replay requires a distinct fresh session")
            prepared["raw"] = raw
            prepared["post_check"] = prepare_task_post_check(
                self.pin, raw, record_evidence=self.record_evidence
            )
            guard = install_host_guard(raw, runtime_pin, host_nproc=self.host_nproc)
            guard.command_timeout = self.test_timeout
            return guard

        guarded = self.runtime.start_guarded(boundary)
        session = prepared["raw"]
        post_check = prepared["post_check"]
        try:
            if patch:
                path = guarded.scratch + "/candidate.patch"
                quoted = shlex.quote(path)
                session.write_file(path, patch)
            if untracked_artifact is not None:
                # One trusted process applies all data BEFORE any tracked candidate edits.
                apply_untracked_deltas(session, untracked_artifact)
            touched = []
            if patch:
                code, out, _ = guarded.exec("git apply --numstat -z -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate is not a valid patch")
                for record in out.split("\x00"):
                    if not record:
                        continue
                    fields = record.split("\t", 2)
                    if len(fields) != 3:
                        raise CandidatePatchRejected("ambiguous patch paths")
                    try:
                        name = relative_path(fields[2])
                    except ValueError as exc:
                        raise CandidatePatchRejected("unsafe patch path") from exc
                    if self.transport._protected(name):
                        raise CandidatePatchRejected("candidate changes protected input: " + name)
                    touched.append(name)
                if not touched:
                    raise CandidatePatchRejected("nonempty patch has no changes")
                self.transport._regular_paths(guarded, touched)
                code, _, _ = guarded.exec("git apply --check -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate patch does not apply")
                _checked(guarded, "git apply -- " + quoted)
                self.transport._regular_paths(guarded, touched)
                _checked(guarded, "rm -- " + quoted)
            # Every candidate-importing invocation uses inherited Landlock/seccomp guard.
            code, out, err = guarded.exec(self.pin.test_command, self.test_timeout)
            evidence = {
                "phase": "frozen_tests",
                "command": self.pin.test_command,
                "exit": code,
                "stdout": out,
                "stderr": err,
                "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
                "kind": "diagnostic_host_test_replay",
                "protected_status": "unknown",
            }
            self.evidence_records.append(evidence)
            if self.record_evidence is not None:
                self.record_evidence(dict(evidence))
            if code == 124:
                raise RuntimeUnavailable("frozen test command timed out")
            self.runtime.verify()
            expected = self.pin.fail_to_pass + self.pin.pass_to_pass
            parsed = parse_pytest_summary(out, expected)
            outcomes = TestEvidence(
                exit_code=code,
                statuses={
                    node: TestStatus(status)
                    for node, status in parsed.items()
                    if status is not None
                },
            ).require(expected)
            post_result = (
                post_check.evaluate(guarded, (code, out, err), timeout=self.test_timeout)
                if post_check is not None
                else {}
            )
            self.runtime.verify()
            return {
                **post_result,
                "diagnostic_passed": post_result.get(
                    "diagnostic_passed",
                    code == 0 and all(value is TestStatus.PASSED for value in outcomes.values()),
                ),
                "test_results": {"exit": code, "stdout": out, "stderr": err},
                "diagnostic_replay": {
                    "kind": "diagnostic_host_test_replay",
                    "protected_status": "unknown",
                    "task_key": self.pin.key,
                    "prepared_ref": self.prepared_ref,
                    "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
                    "changed_files": sorted(set(touched)),
                    "untracked_artifact": untracked_artifact,
                    "artifact_scope": "tracked and untracked code deltas; omissions explicit",
                    "statuses": outcomes,
                    "runtime_kind": self.runtime.pin.kind,
                    "repository_sha256": self.runtime.pin.repository_sha256,
                    "venv_sha256": self.runtime.pin.venv_sha256,
                    "guard_attestation": guarded.attestation,
                    "limitations": [
                        "candidate can tamper with same-process pytest evidence",
                        "target environment/package changes are not replayed",
                        "host Python runtime is separately pinned; not the original container",
                    ],
                },
            }
        finally:
            guarded.stop()
