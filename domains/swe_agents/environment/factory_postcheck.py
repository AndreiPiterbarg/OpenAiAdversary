"""Required supplementary diagnostics for the pinned Factory Boy regression.

Prepare in trusted fresh replay state before applying/importing candidate code, then
run with the guarded candidate session after its frozen tests. Both test groups must
pass to report a diagnostic pass. Neither group authenticates arbitrary Python:
candidate code shares pytest's interpreter and can forge its status output. This
adapter never grants protected status, even when all reported tests pass.

The separate FactoryArtifactReplay admits the complete source closure against a
finite repair grammar before execution. Its trusted execution-boundary callback is
also required. A candidate-provided admission receipt cannot substitute for either.
Exporting code alone does not evaluate target package, policy, or environment state.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domains.swe_agents.environment.factory_replay import TEST_COMMAND, TEST_PATCH_SHA256
from domains.swe_agents.environment.factory_verifier import F2P, KEY, P2P, FactoryFinalVerifier
from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.environment.test_results import TestStatus, parse_test_results

CHALLENGES_SHA256 = "688eb8789a341b012364d1f4c395ec36b2883fd2f8ebd97af1654303844cbbd4"
CHALLENGE_IDS = (
    *(f"test_maybe_preserves_decider_defaults[{decision}]" for decision in ("False", "True")),
    *(
        f"test_faker_decider_preserves_locale_and_branch[{locale}-{decision}]"
        for locale in ("None", "fr_FR", "de_DE")
        for decision in ("False", "True")
    ),
    *(
        f"test_nested_maybe_evaluates_only_selected_branch[{outer}-{inner}]"
        for outer in ("False", "True")
        for inner in ("False", "True")
    ),
    *(
        f"test_selected_branch_gets_overrides_without_overriding_decider[{decision}]"
        for decision in ("False", "True")
    ),
)
_ROOT = re.compile(r"\./\.prun-factory-postcheck-[A-Za-z0-9]+")
_PATH = re.compile(r"\.prun-factory-postcheck-[A-Za-z0-9]+/test_factory_semantics\.py")
_PREFIX = "pytest --rootdir=. -o addopts= --no-header -rA --tb=line --color=no -p no:cacheprovider "


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def combine_factory_results(
    frozen: tuple[int, str, str],
    supplementary: tuple[int, str, str],
    *,
    challenge_path: str,
) -> dict[str, Any]:
    """Combine complete observations; malformed evidence raises instead of passing.

    This public parser is deliberately incapable of returning a protected pass.
    Exit one with all expected statuses passed still cannot count as a pass.
    """
    if not _PATH.fullmatch(challenge_path):
        raise ValueError("invalid supplementary challenge path")
    if frozen[0] == 124 or supplementary[0] == 124:
        raise RuntimeUnavailable("required Factory test command timed out")
    expected = tuple(f"{challenge_path}::{node}" for node in CHALLENGE_IDS)
    frozen_statuses = parse_test_results(frozen[0], frozen[1]).require(F2P + P2P)
    extra_statuses = parse_test_results(supplementary[0], supplementary[1]).require(expected)
    frozen_passed = frozen[0] == 0 and all(s == TestStatus.PASSED for s in frozen_statuses.values())
    extra_passed = supplementary[0] == 0 and all(
        s == TestStatus.PASSED for s in extra_statuses.values()
    )
    return {
        "diagnostic_passed": frozen_passed and extra_passed,
        "protected_status": "unknown",
        "protected_clean_pass": None,
        "supplementary_results": {
            "exit": supplementary[0],
            "stdout": supplementary[1],
            "stderr": supplementary[2],
            "statuses": extra_statuses,
        },
        "post_checks": {
            "kind": "factory_required_semantic_diagnostics_v1",
            "required": True,
            "frozen_passed": frozen_passed,
            "supplementary_passed": extra_passed,
            "frozen_statuses": frozen_statuses,
            "expected_supplementary": expected,
            "challenges_sha256": CHALLENGES_SHA256,
            "authenticated_test_evidence": False,
            "limitations": [
                "arbitrary candidate Python can forge same-process pytest evidence",
                "no finite source admission was performed by this diagnostic adapter",
                "target environment, policy, and packages are not evaluated",
            ],
        },
    }


@dataclass(frozen=True)
class FactoryPostCheck:
    """Prepared challenge source and exact IDs owned by the trusted controller."""

    challenge_path: str
    record_evidence: Callable[[dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        if not _PATH.fullmatch(self.challenge_path):
            raise ValueError("invalid supplementary challenge path")

    def require_protected(self) -> None:
        raise RuntimeUnavailable(
            "Factory supplementary pytest remains unauthenticated for arbitrary Python"
        )

    def evaluate(
        self,
        guarded_session: Session,
        frozen_result: tuple[int, str, str],
        *,
        timeout: float = 120,
    ) -> dict[str, Any]:
        if not 0 < timeout <= 900:
            raise ValueError("invalid supplementary timeout")
        # Integrity checks can detect ordinary edits but cannot authenticate a
        # candidate-controlled interpreter; the outcome remains diagnostic.
        if _sha(guarded_session.read_file(self.challenge_path)) != CHALLENGES_SHA256:
            raise RuntimeUnavailable("supplementary challenge source changed")
        command = _PREFIX + shlex.quote(self.challenge_path)
        result = guarded_session.exec(command, timeout)
        if self.record_evidence is not None:
            self.record_evidence(
                {
                    "phase": "supplementary_tests",
                    "command": command,
                    "exit": result[0],
                    "stdout": result[1],
                    "stderr": result[2],
                    "kind": "factory_required_semantic_diagnostics_v1",
                    "protected_status": "unknown",
                    "challenges_sha256": CHALLENGES_SHA256,
                }
            )
        if _sha(guarded_session.read_file(self.challenge_path)) != CHALLENGES_SHA256:
            raise RuntimeUnavailable("supplementary challenge source changed during execution")
        return combine_factory_results(frozen_result, result, challenge_path=self.challenge_path)


def prepare_task_post_check(
    pin: TaskPin,
    trusted_fresh_session: Session,
    *,
    record_evidence: Callable[[dict[str, Any]], None] | None = None,
) -> FactoryPostCheck | None:
    """Called before candidate edits/imports; unsupported tasks have no adapter."""
    if pin.key != KEY:
        return None
    FactoryFinalVerifier(pin.model_dump(mode="json"))
    if pin.test_command != TEST_COMMAND or _sha(pin.test_patch or "") != TEST_PATCH_SHA256:
        raise RuntimeUnavailable("Factory frozen command or test patch differs")
    source = (Path(__file__).parents[1] / "scripts/factory_challenges.py").read_text()
    if _sha(source) != CHALLENGES_SHA256:
        raise RuntimeUnavailable("trusted Factory challenges differ from the mutation gate")
    code, root, error = trusted_fresh_session.exec(
        "mktemp -d ./.prun-factory-postcheck-XXXXXXXX", 30
    )
    root = root.strip()
    if code or not _ROOT.fullmatch(root):
        raise RuntimeUnavailable("cannot prepare Factory supplementary directory: " + error[-500:])
    path = root[2:] + "/test_factory_semantics.py"
    trusted_fresh_session.write_file(path, source)
    if _sha(trusted_fresh_session.read_file(path)) != CHALLENGES_SHA256:
        raise RuntimeUnavailable("Factory supplementary transport differs")
    # Expected IDs are pinned, not discovered from candidate-controlled collection.
    return FactoryPostCheck(path, record_evidence)
