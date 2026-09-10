"""Evidence attached to a probe: rates, excess, transfer, prevalence."""

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.model import LicenseClass
from adversary.stats.excess import ExcessEstimate
from adversary.stats.importance import PrevalenceEstimate
from adversary.stats.mobius import MobiusSynergy
from adversary.stats.rates import RateEstimate


class TransferResult(FrozenModel):
    """Whether a mode reproduces on another model, and how severely."""

    model_id: str
    license: LicenseClass
    mode_failure_rate: float
    control_failure_rate: float
    n: int
    severity_ratio: float = Field(description="This model's (mode - control) gap over the target's")


class HeldOutRef(FrozenModel):
    """The real held-out set a probe was confirmed on."""

    corpus_fingerprint: str
    sources: tuple[str, ...]
    condition: Cell
    n: int


class Evidence(FrozenModel):
    """Everything measured about a probe's region."""

    excess: ExcessEstimate | None = None
    mode_rate: RateEstimate | None = Field(
        default=None, description="Failure rate inside the region"
    )
    control_rate: RateEstimate | None = Field(
        default=None, description="Failure rate on matched non-region items"
    )
    silence: float | None = Field(
        default=None, description="Share of region failures reported as successes"
    )
    prevalence: PrevalenceEstimate | None = Field(default=None, description="From outside the loop")
    confirmatory: MobiusSynergy | None = Field(
        default=None, description="Rate-scale Möbius synergy from the branch design (A5)"
    )
    transfer: tuple[TransferResult, ...] = ()

    @property
    def severity_points(self) -> float | None:
        """Mode minus control failure rate in percentage points, if both are known."""
        if self.mode_rate is None or self.control_rate is None:
            return None
        return 100.0 * (self.mode_rate.rate - self.control_rate.rate)

    @property
    def systematicity(self) -> float | None:
        """Failure rate inside the region; 0.95 is fixable with data, 0.25 is noise."""
        return self.mode_rate.rate if self.mode_rate else None
