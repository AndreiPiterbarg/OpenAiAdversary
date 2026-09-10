"""Hashing and exact test-status parsing for externally produced gold receipts.

These checks validate a task before exposure to an agent. They do not make an agent's
mutable final filesystem a trusted oracle, nor attest an image's supply-chain safety.
"""

import hashlib
import re
from pathlib import Path

from domains.swe_agents.environment.test_results import TestEvidence, TestStatus


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
            value.update(chunk)
    return value.hexdigest()


def expected_results(exit_code: int, text: str, expected: tuple[str, ...]) -> TestEvidence:
    """Use expected IDs as literal strings, including parameter IDs with spaces."""
    statuses: dict[str, TestStatus] = {}
    conflicts: set[str] = set()
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    for line in text.splitlines():
        line = line.strip()
        for node in sorted(expected, key=len, reverse=True):
            found = None
            for status in TestStatus:
                prefix = status.value + " " + node
                if line == prefix or line.startswith(prefix + " - "):
                    found = status
                if re.fullmatch(
                    re.escape(node) + r"\s+" + status.value + r"(?:\s+\[\s*\d+%\])?", line
                ):
                    found = status
                if found is not None:
                    break
            if found is not None:
                if node in statuses and statuses[node] != found:
                    conflicts.add(node)
                statuses[node] = found
                break
    return TestEvidence(exit_code=exit_code, statuses=statuses, conflicts=tuple(sorted(conflicts)))
