"""The unit row of every statistic: one instance, one model, one verdict.

Episodes are written only by the execution harness from measured outcomes. Nothing in the
search layer constructs one, which is what lets the kill log be derived rather than
narrated. An instance that produced no episode is an :class:`Unreached` record, by stage.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.model import Usage
from adversary.core.util import utc_now
from adversary.core.verify import Verdict

Stage = Literal["generate", "build", "run", "verify"]


class Episode(FrozenModel):
    """One measured outcome."""

    id: str
    instance_id: str
    cell: Cell = Field(description="Full configuration the instance realised")
    seed: int
    model_id: str
    target_pin: str | None = None
    probe_id: str | None = Field(default=None, description="Probe that generated the instance")
    arm: str | None = Field(
        default=None, description="'control' or 'treatment' when part of a minimal pair"
    )
    verdict: Verdict
    claimed_success: bool | None = Field(default=None, description="Target's self-report")
    verifier: str = Field(description="Verifier identity and version, 'module:Class@version'")
    resource: str | None = Field(
        default=None, description="Copied from the instance; the bootstrap cluster"
    )
    usage: Usage = Field(default_factory=Usage)
    build_seconds: float = Field(
        default=0.0, ge=0.0, description="Environment build time; counts toward compute-hours"
    )
    truncated: bool = False
    realised: bool = Field(
        default=True,
        description=(
            "Every scheduled perturbation was applied. Unrealised episodes do not measure their "
            "cell and are excluded from cell statistics, but counted and reported."
        ),
    )
    planted: bool = Field(
        default=False, description="Verdict was forced by a planted mode; excluded from every claim"
    )
    recorded_at: datetime = Field(default_factory=utc_now)

    @property
    def failed(self) -> bool:
        """Verifier said fail."""
        return not self.verdict.passed

    @property
    def silent_failure(self) -> bool:
        """The target reported success and the environment says otherwise."""
        return self.claimed_success is True and self.failed

    @property
    def honest(self) -> bool | None:
        """Whether self-report matched the verdict; ``None`` if no self-report was elicited."""
        if self.claimed_success is None:
            return None
        return self.claimed_success == self.verdict.passed

    @property
    def measurable(self) -> bool:
        """Counts toward a cell statistic: not planted and realised."""
        return self.realised and not self.planted


class Unreached(FrozenModel):
    """An instance that produced no episode. Counted as not reached, never as a failure."""

    instance_id: str
    cell: Cell
    stage: Stage = Field(description="Where it stopped: generate, build, run or verify")
    reason: str
    recorded_at: datetime = Field(default_factory=utc_now)
