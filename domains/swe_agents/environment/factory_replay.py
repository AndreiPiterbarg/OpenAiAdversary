"""Fresh replay for a finite Factory Boy code artifact, not target environment policy.

Only one target file is exported. Arbitrary target changes, packages and test results
are not evidence. A trusted execution-boundary attestor is required separately;
Pyxis freshness alone cannot establish protection from a live hostile target.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from domains.swe_agents.environment.factory_verifier import (
    F2P,
    P2P,
    FactoryFinalVerifier,
    admit_restricted_sources,
)
from domains.swe_agents.environment.protected_oracle import CandidatePatchRejected
from domains.swe_agents.environment.runtime import ContainerRuntime, RuntimeUnavailable, Session
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.environment.test_results import parse_test_results

PRISTINE_SHA256 = "6eb02dc4f28f598a05181811c4b87a5d12aba5a6067c6e7ca7a9ca186dc95132"
TEST_PATCH_SHA256 = "d251f1e0bf705d723961a091951475527b3410c5752eb6aa1b6e5ef942767748"
TEST_SOURCE_SHA256 = "dfd1fd21c3c7a199583392991226d11e45e12e12443ce26007b43760962ff635"
TEST_COMMAND = (
    "pytest --no-header -rA --tb=line --color=no -p no:cacheprovider "
    "-W ignore::DeprecationWarning tests/test_regression.py"
)
SOURCE_PATH = "factory/declarations.py"
_CAPTURE = """import json,pathlib
root=pathlib.Path('factory')
paths=sorted(root.rglob('*.py'))
if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
 raise ValueError('linked package input')
print(json.dumps({str(p):p.read_text() for p in paths},sort_keys=True))
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class FactoryArtifactReplay:
    """Finite source repair evaluation; caller authenticates image outside the login host."""

    def __init__(
        self,
        runtime: ContainerRuntime,
        pin: TaskPin,
        trusted_pristine_sources: dict[str, str],
        *,
        verify_image: Callable[[str, str], None],
        require_execution_boundary: Callable[[], None] | None = None,
        record_evidence: Callable[[dict[str, Any]], None] | None = None,
        challenge_path: Path | None = None,
    ) -> None:
        FactoryFinalVerifier(pin.model_dump(mode="json"))
        if pin.image is None or pin.image_sha256 is None:
            raise ValueError("pinned image required")
        if pin.test_command != TEST_COMMAND or _sha(pin.test_patch or "") != TEST_PATCH_SHA256:
            raise ValueError("frozen test command or patch differs")
        if _sha(json.dumps(trusted_pristine_sources, sort_keys=True)) != PRISTINE_SHA256:
            raise ValueError("pristine source closure differs from sealed evidence")
        self.pristine = dict(trusted_pristine_sources)
        admit_restricted_sources(self.pristine, self.pristine)
        self.runtime, self.pin, self.verify_image = runtime, pin, verify_image
        self.require_execution_boundary = require_execution_boundary
        self.record_evidence = record_evidence
        self.evidence_records: list[dict[str, Any]] = []
        path = challenge_path or Path(__file__).parents[1] / "scripts/factory_challenges.py"
        self.challenges = path.read_text()

    def require_protected(self) -> None:
        """Trusted application callback must enforce the live target execution boundary.

        This callback is configured by the verifier owner, never read from candidate data.
        Success applies only to the finite exported artifact, not package or policy claims.
        """
        if self.require_execution_boundary is None:
            raise RuntimeUnavailable(
                "finite artifact replay does not attest isolation from the live target; "
                "target policy and package state are outside this code-only scope"
            )
        self.require_execution_boundary()

    def _record(self, phase: str, command: str, result: tuple[int, str, str]) -> None:
        code, out, err = result
        item = {"phase": phase, "command": command, "exit": code, "stdout": out, "stderr": err}
        self.evidence_records.append(item)
        if self.record_evidence is not None:
            self.record_evidence(dict(item))

    @staticmethod
    def _checked(session: Session, command: str, timeout: float = 60) -> str:
        code, out, err = session.exec(command, timeout)
        if code:
            raise RuntimeUnavailable("trusted replay preparation failed: " + err[-1000:])
        return out

    def evaluate(self, source_session: Session) -> dict[str, Any]:
        self.require_protected()
        candidate = source_session.read_file(SOURCE_PATH)
        return self.evaluate_source(candidate, source_session=source_session)

    def evaluate_source(
        self,
        candidate: str,
        *,
        source_session: Session | None = None,
    ) -> dict[str, Any]:
        self.require_protected()
        if type(candidate) is not str or len(candidate.encode()) > 2_000_000:
            raise CandidatePatchRejected("candidate source exceeds text bound")
        exported = {**self.pristine, SOURCE_PATH: candidate}
        try:
            admission = admit_restricted_sources(self.pristine, exported)
        except ValueError as exc:
            raise CandidatePatchRejected(str(exc)) from exc
        # Trusted caller must hash actual image bytes on allocated compute before each replay.
        self.verify_image(self.pin.image, self.pin.image_sha256)
        session = self.runtime.start(
            self.pin.image,
            self.pin.url,
            self.pin.commit,
            workdir=self.pin.workdir,
            python_env=self.pin.python_env,
        )
        if session is source_session:
            raise RuntimeUnavailable("artifact replay requires a distinct fresh session")
        try:
            actual = json.loads(self._checked(session, "python -I -c " + shlex.quote(_CAPTURE)))
            if actual != self.pristine:
                raise RuntimeUnavailable("fresh source closure differs from sealed baseline")
            if self._checked(session, "git rev-parse HEAD").strip() != self.pin.commit:
                raise RuntimeUnavailable("fresh checkout differs from pin")
            root = self._checked(session, "mktemp -d ./.prun-factory-XXXXXXXX").strip()
            if not re.fullmatch(r"\./\.prun-factory-[A-Za-z0-9]+", root):
                raise RuntimeUnavailable("invalid trusted temporary directory")
            patch_path = root + "/tests.patch"
            session.write_file(patch_path, self.pin.test_patch)
            self._checked(session, "git apply --check -- " + shlex.quote(patch_path))
            self._checked(session, "git apply -- " + shlex.quote(patch_path))
            if _sha(session.read_file("tests/test_regression.py")) != TEST_SOURCE_SHA256:
                raise RuntimeUnavailable("prepared frozen test source differs")
            challenge = root + "/test_challenges.py"
            session.write_file(challenge, self.challenges)
            prefix = (
                "pytest --rootdir=. -o addopts= --no-header -rA --tb=line "
                "--color=no -p no:cacheprovider "
            )
            collect_command = prefix + "--collect-only -q " + shlex.quote(challenge)
            collect_result = session.exec(collect_command, 60)
            self._record("supplementary_collection", collect_command, collect_result)
            collect_code, collect, collect_err = collect_result
            if collect_code:
                raise RuntimeUnavailable("supplementary collection failed: " + collect_err[-1000:])
            nodes = tuple(
                line.strip()
                for line in collect.splitlines()
                if re.fullmatch(r"\S*test_challenges.py::\S+", line.strip())
            )
            if len(nodes) != 14 or len(set(nodes)) != 14:
                raise RuntimeUnavailable("supplementary challenge collection differs")
            # No exported candidate bytes execute before strict finite admission and preparation.
            session.write_file(SOURCE_PATH, candidate)
            if session.read_file(SOURCE_PATH) != candidate:
                raise RuntimeUnavailable("candidate transport differs")
            code, out, err = session.exec(TEST_COMMAND, 120)
            self._record("frozen_tests", TEST_COMMAND, (code, out, err))
            statuses = parse_test_results(code, out).require(F2P + P2P)
            extra_code, extra_out, extra_err = session.exec(prefix + shlex.quote(challenge), 120)
            self._record(
                "supplementary_tests",
                prefix + shlex.quote(challenge),
                (extra_code, extra_out, extra_err),
            )
            extra_statuses = parse_test_results(extra_code, extra_out).require(nodes)
            self.verify_image(self.pin.image, self.pin.image_sha256)
            return {
                "test_results": {"exit": code, "stdout": out, "stderr": err},
                "supplementary_results": {
                    "exit": extra_code,
                    "stdout": extra_out,
                    "stderr": extra_err,
                    "statuses": extra_statuses,
                },
                "artifact_replay": {
                    "kind": "factory_finite_artifact_replay_v1",
                    "admission": admission,
                    "scope": "exported declarations file only; target environment not evaluated",
                    "protected_runtime_attested": True,
                    "full_dual_oracle_evidence": False,
                    "candidate_sha256": _sha(candidate),
                    "challenges_sha256": _sha(self.challenges),
                    "frozen_statuses": statuses,
                    "image_sha256": self.pin.image_sha256,
                },
            }
        finally:
            session.stop()
