"""Anti-gaming, at build time. Week-one items, not later hardening.

- Strip git history, remote refs and reflog: agents mine them.
- Mutation-test every suite; discard tasks where a trivial mutant survives.
- Contamination check against public benchmark instance ids and the target's training cutoff.
- Canary strings in every eval task (generated in :mod:`generator`).
"""

from collections.abc import Iterable

from pydantic import Field

from adversary.core.config import FrozenModel
from domains.swe_agents.environment.runtime import Session


class AuditReport(FrozenModel):
    """What the build-time audit established for one task."""

    git_stripped: bool = Field(strict=True)
    mutation_score: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Fraction of declared trivial mutants the suite kills",
    )
    surviving_trivial_mutants: int | None = Field(default=None, ge=0, strict=True)
    tested_trivial_mutants: int = Field(default=0, ge=0, strict=True)
    contaminated: bool = Field(strict=True)
    notes: str = ""

    @property
    def valid(self) -> bool:
        """All declared audit evidence exists and passes; absent evidence is not success."""
        try:
            report = type(self).model_validate(self.model_dump(mode="python"))
        except (TypeError, ValueError):
            return False
        return (
            report.git_stripped
            and not report.contaminated
            and report.tested_trivial_mutants > 0
            and report.surviving_trivial_mutants == 0
            and report.mutation_score == 1.0
        )


def strip_git_history(session: Session) -> bool:
    """Remove ``.git`` entirely and re-initialise with a single snapshot commit; nothing to mine.

    This realises the pinned contamination axis (``git_history_contains_answer = stripped``)."""
    command = (
        "rm -rf .git && git init -q && git add -A && "
        "git -c user.email=a@b -c user.name=a commit -qm snapshot"
    )
    code, _, _ = session.exec(command, timeout=120)
    return code == 0


def mutation_test(session: Session, test_command: str, targets: Iterable[str]) -> tuple[float, int]:
    """Refuse unregistered in-place mutation; the audit needs explicit fresh-session cases."""
    raise ValueError(
        "use run_mutation_audit with explicit mutant patches and a fresh prepared-session factory"
    )


def contamination_check(instance_key: str, public_ids: Iterable[str]) -> bool:
    """Whether the task overlaps a public benchmark instance."""
    return instance_key in set(public_ids)
