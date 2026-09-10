"""Exact per-test outcomes; incomplete or contradictory evidence cannot score a target."""

import re
from enum import StrEnum

from pydantic import Field

from adversary.core.config import FrozenModel


class TestEvidenceError(ValueError):
    """Test execution or its status evidence is incomplete: record as unreached."""


class TestStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    XFAIL = "XFAIL"
    XPASS = "XPASS"


class TestEvidence(FrozenModel):
    """Command result and exact node identifiers, retaining parsing refusals."""

    exit_code: int
    statuses: dict[str, TestStatus] = Field(default_factory=dict)
    conflicts: tuple[str, ...] = ()

    def require(self, identifiers: tuple[str, ...]) -> dict[str, TestStatus]:
        if self.exit_code not in (0, 1):
            raise TestEvidenceError(f"invalid test command exit: {self.exit_code}")
        if not identifiers or len(set(identifiers)) != len(identifiers):
            raise TestEvidenceError("required test identifiers must be nonempty and distinct")
        missing = set(identifiers) - self.statuses.keys()
        if missing or self.conflicts:
            raise TestEvidenceError(f"missing={sorted(missing)} conflicting={list(self.conflicts)}")
        if any(self.statuses[t] not in (TestStatus.PASSED, TestStatus.FAILED) for t in identifiers):
            raise TestEvidenceError("required test skipped, errored or marked as expected failure")
        if self.exit_code == 0 and any(
            s in (TestStatus.FAILED, TestStatus.ERROR) for s in self.statuses.values()
        ):
            raise TestEvidenceError("zero exit contradicts a failing test status")
        return {t: self.statuses[t] for t in identifiers}


def parse_test_results(exit_code: int, stdout: str) -> TestEvidence:
    """Parse anchored pytest verbose or short-summary records, never name substrings.

    Repeated identical summary/verbose statuses are harmless; contradictions are retained.
    Other test runners need their own adapter rather than being guessed from arbitrary text.
    """
    statuses: dict[str, TestStatus] = {}
    conflicts: set[str] = set()
    status = "PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"
    verbose = re.compile(rf"^(\S+)\s+({status})(?:\s+\[\s*\d+%\])?\s*$")
    summary = re.compile(rf"^({status})\s+(\S+)(?:\s+-\s+.*)?$")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    for line in clean.splitlines():
        match = verbose.fullmatch(line.strip())
        if match:
            node, value = match.groups()
        else:
            match = summary.fullmatch(line.strip())
            if not match:
                continue
            value, node = match.groups()
        parsed = TestStatus(value)
        if node in statuses and statuses[node] != parsed:
            conflicts.add(node)
        statuses[node] = parsed
    return TestEvidence(exit_code=exit_code, statuses=statuses, conflicts=tuple(sorted(conflicts)))
