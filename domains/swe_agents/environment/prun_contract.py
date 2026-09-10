"""Conservative offline classification of baseline and gold pytest evidence.

Logs must come from the recorded test invocation. This module neither authenticates
logs nor executes tests. Missing evidence is never treated as a successful test.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

_STATUS = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (.+)$")


def _identifiers(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("test identifiers must be a collection")
    result = tuple(values)
    for node in result:
        if (
            not isinstance(node, str)
            or not node
            or node != node.strip()
            or "\n" in node
            or "\r" in node
            or ("[" in node and not node.endswith("]"))
        ):
            raise ValueError("test identifiers must be complete single-line strings")
    if len(set(result)) != len(result):
        raise ValueError("duplicate test identifiers")
    return result


def parse_pytest_summary(text: str, expected: Iterable[str]) -> dict[str, str | None]:
    """Return exact expected statuses, or None for missing/conflicting evidence.

    Parameter spaces are preserved. Only FAILED/ERROR can carry pytest's
    `` - reason`` suffix; PASSED lines must match in full. A bracket in a
    parameterized test's reason is ambiguous with a longer parameter value and
    is conservatively left unresolved. Unrelated lines do not supply evidence.
    """
    nodes = _identifiers(expected)
    seen: dict[str, set[str]] = {node: set() for node in nodes}
    for line in text.splitlines():
        match = _STATUS.fullmatch(line)
        if not match:
            continue
        status, payload = match.groups()
        if payload in seen:
            seen[payload].add(status)
            continue
        if status not in {"FAILED", "ERROR"}:
            continue
        matches = []
        for node in nodes:
            if not payload.startswith(node + " - "):
                continue
            suffix = payload[len(node) + 3 :]
            if "[" in node and any(char in suffix for char in "[]"):
                # Ambiguous evidence must also invalidate any prior status.
                seen[node].update({"AMBIGUOUS", status})
            else:
                matches.append(node)
        if len(matches) == 1:
            seen[matches[0]].add(status)
        elif matches:
            # A single log line cannot prove which of multiple identifiers ran.
            for node in matches:
                seen[node].update({"AMBIGUOUS", status})
    return {
        node: next(iter(statuses)) if len(statuses) == 1 else None
        for node, statuses in seen.items()
    }


@dataclass(frozen=True)
class PhaseEvidence:
    log: str
    exit_code: int | None
    completed: bool = True


@dataclass(frozen=True)
class GoldVerdict:
    valid: bool | None
    status: str
    reason: str
    baseline_statuses: dict[str, str | None]
    gold_statuses: dict[str, str | None]


def verify_gold(
    fail_to_pass: Iterable[str],
    pass_to_pass: Iterable[str],
    baseline: PhaseEvidence,
    gold: PhaseEvidence,
) -> GoldVerdict:
    """Classify complete two-arm evidence; keep execution uncertainty unknown.

    Baseline F2P tests must fail/error and P2P tests must pass. All expected gold
    tests and the complete gold command must pass. Gold exit 1 is invalid even
    when all expected tests passed, because the full suite failed. Exit codes
    outside 0/1 indicate unresolved execution or
    collection evidence, even when partial logs contain expected test results.
    """
    f2p, p2p = _identifiers(fail_to_pass), _identifiers(pass_to_pass)
    if not f2p or set(f2p) & set(p2p):
        raise ValueError("F2P must be nonempty and disjoint from P2P")
    expected = f2p + p2p
    before = parse_pytest_summary(baseline.log, expected)
    after = parse_pytest_summary(gold.log, expected)

    def result(valid: bool | None, status: str, reason: str) -> GoldVerdict:
        return GoldVerdict(valid, status, reason, before, after)

    if any(
        phase.completed is not True
        or type(phase.exit_code) is not int
        or phase.exit_code not in {0, 1}
        for phase in (baseline, gold)
    ):
        return result(None, "unknown", "execution or collection did not complete normally")
    if any(
        value not in {"PASSED", "FAILED", "ERROR"} for value in (*before.values(), *after.values())
    ):
        return result(None, "unknown", "expected evidence is missing, conflicting, or skipped")
    # Inconsistent exit/status combinations cannot establish a semantic label.
    if any(
        phase.exit_code == 0 and any(value != "PASSED" for value in statuses.values())
        for phase, statuses in ((baseline, before), (gold, after))
    ):
        return result(None, "unknown", "test statuses contradict successful process exit")
    if any(before[node] != "PASSED" for node in p2p):
        return result(False, "invalid", "baseline P2P failure")
    if any(before[node] not in {"FAILED", "ERROR"} for node in f2p):
        return result(False, "invalid", "baseline F2P did not fail")
    if any(after[node] != "PASSED" for node in expected):
        return result(False, "invalid", "gold did not pass every expected test")
    if gold.exit_code == 1:
        return result(False, "invalid", "gold command failed outside the expected test set")
    if baseline.exit_code != 1 or gold.exit_code != 0:
        return result(None, "unknown", "process exit does not establish the required outcome")
    return result(True, "verified", "all expected transitions and process exits match")
