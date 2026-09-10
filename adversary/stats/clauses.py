"""A clause decomposition is a reviewed coordinate system, not a model assertion."""

from pydantic import Field

from adversary.core.config import FrozenModel


class ClauseAudit(FrozenModel):
    """Independent review bound to exact program and independently meaningful switches.

    Receipt verification belongs to the caller's evidence boundary. Merely recording nonzero
    singleton effects does not establish independence or defeat stage/arm decompositions.
    """

    program_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    clauses: tuple[str, ...]
    reviewer: str = Field(min_length=1)
    independent_switches: bool
    rationale: str = Field(min_length=1)

    def require(self, clauses: tuple[str, ...], program_digest: str | None) -> None:
        if (
            not self.independent_switches
            or self.clauses != clauses
            or program_digest != self.program_digest
        ):
            raise ValueError(
                "excess refused: clause decomposition lacks matching independent review"
            )
