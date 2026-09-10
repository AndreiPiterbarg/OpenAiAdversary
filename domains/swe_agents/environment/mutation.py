"""Finite, explicitly registered mutation controls on fresh prepared task sessions.

The caller supplies authored negative controls and the trusted test command. This measures
only those controls; it does not certify the suite against all possible oracle weaknesses.
"""

import math
import re
import shlex
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.util import sha256_json
from domains.swe_agents.environment.gold import expected_results
from domains.swe_agents.environment.runtime import Session
from domains.swe_agents.environment.test_results import TestStatus, parse_test_results


class MutationCase(FrozenModel):
    id: str = Field(min_length=1)
    patch: str = Field(min_length=1)


class MutationOutcome(FrozenModel):
    id: str
    outcome: Literal["baseline_passed", "killed", "survived", "unresolved"]
    stage: str
    reason: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class MutationAudit(FrozenModel):
    design_digest: str
    baseline: MutationOutcome
    mutants: tuple[MutationOutcome, ...]

    @property
    def complete(self) -> bool:
        return (
            self.baseline.outcome == "baseline_passed"
            and bool(self.mutants)
            and all(row.outcome in ("killed", "survived") for row in self.mutants)
        )

    @property
    def score(self) -> float | None:
        return (
            sum(row.outcome == "killed" for row in self.mutants) / len(self.mutants)
            if self.complete
            else None
        )

    @property
    def survivors(self) -> int | None:
        return sum(row.outcome == "survived" for row in self.mutants) if self.complete else None


def run_mutation_audit(
    start: Callable[[], Session],
    test_command: str,
    expected_tests: tuple[str, ...],
    mutants: Sequence[MutationCase],
    *,
    timeout: float = 120,
) -> MutationAudit:
    """Run baseline and each frozen mutant fresh; errors remain unresolved, never killed.

    ``start`` must return a task prepared at the same pinned, passing baseline, including
    trusted tests. The command must select exactly the declared expected tests.
    No target session is reused, and every returned session is closed.
    This is an execution instrument, not an authenticated receipt consumer.
    """
    if not test_command.strip() or "\x00" in test_command:
        raise ValueError("a trusted test command is required")
    if not expected_tests or len(set(expected_tests)) != len(expected_tests):
        raise ValueError("distinct nonempty expected test IDs are required")
    if any(not isinstance(node, str) or not node.strip() for node in expected_tests):
        raise ValueError("expected test IDs must be nonblank strings")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    cases = tuple(MutationCase.model_validate(case.model_dump()) for case in mutants)
    if not cases or len({case.id for case in cases}) != len(cases):
        raise ValueError("a nonempty distinct mutant schedule is required")
    if any(not case.id.strip() or not case.patch.strip() or "\x00" in case.patch for case in cases):
        raise ValueError("mutant IDs and patches must be nonblank NUL-free text")
    design = sha256_json(
        {
            "command": test_command,
            "expected": expected_tests,
            "cases": [case.model_dump() for case in cases],
            "timeout": timeout,
        }
    )
    sessions = []

    def execute(case: MutationCase | None) -> MutationOutcome:
        name = case.id if case else "baseline"
        session = None
        stage, code, out, err = "start", None, "", ""
        try:
            session = start()
            if any(session is previous for previous in sessions):
                session = None
                raise ValueError("mutation audit requires a fresh session for every case")
            sessions.append(session)
            if case is not None:
                stage = "apply"
                code, path, err = session.exec("mktemp /tmp/pcode-mutant-XXXXXXXX", timeout)
                path = path.strip()
                if code or not re.fullmatch(r"/tmp/pcode-mutant-[A-Za-z0-9]+", path):
                    raise ValueError("mutant patch transport failed")
                session.write_file(path, case.patch)
                quoted = shlex.quote(path)
                for command in ("git apply --check -- ", "git apply -- ", "rm -- "):
                    code, out, err = session.exec(command + quoted, timeout)
                    if code:
                        raise ValueError("mutant patch did not apply cleanly")
            stage = "tests"
            code, out, err = session.exec(test_command, timeout)
            observed = parse_test_results(code, out + "\n" + err)
            if set(observed.statuses) - set(expected_tests) or observed.conflicts:
                raise ValueError("test command reported undeclared or conflicting test outcomes")
            statuses = expected_results(code, out + "\n" + err, expected_tests).require(
                expected_tests
            )
            passed = code == 0 and all(value is TestStatus.PASSED for value in statuses.values())
            failed = code == 1 and any(value is TestStatus.FAILED for value in statuses.values())
            if not passed and not failed:
                raise ValueError("test command and expected statuses disagree")
            result = MutationOutcome(
                id=name,
                stage=stage,
                exit_code=code,
                stdout=out,
                stderr=err,
                outcome=("baseline_passed" if passed else "unresolved")
                if case is None
                else ("survived" if passed else "killed"),
                reason="" if case or passed else "baseline must pass",
            )
        except Exception as exc:  # noqa: BLE001 - every scheduled case retains its disposition
            result = MutationOutcome(
                id=name,
                outcome="unresolved",
                stage=stage,
                reason=repr(exc),
                exit_code=code,
                stdout=out,
                stderr=err,
            )
        finally:
            if session is not None:
                try:
                    session.stop()
                except Exception as exc:  # noqa: BLE001 - teardown is execution evidence too
                    result = MutationOutcome(
                        id=name,
                        outcome="unresolved",
                        stage="stop",
                        reason=repr(exc),
                        exit_code=code,
                        stdout=out,
                        stderr=err,
                    )
        return result

    baseline = execute(None)
    outcomes = tuple(
        execute(case)
        if baseline.outcome == "baseline_passed"
        else MutationOutcome(
            id=case.id,
            outcome="unresolved",
            stage="baseline",
            reason="baseline did not establish a passing suite",
        )
        for case in cases
    )
    return MutationAudit(design_digest=design, baseline=baseline, mutants=outcomes)
