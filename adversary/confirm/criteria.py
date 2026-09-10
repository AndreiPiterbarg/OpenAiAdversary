"""What it takes for a finding to become a mode. Defaults are the proof's numbers (spec §10)."""

from typing import Literal

from pydantic import Field

from adversary.core.config import StrictModel


class ConfirmationCriteria(StrictModel):
    """Thresholds a real-data confirmation must meet."""

    min_items: int = Field(
        default=300, ge=1, strict=True, description="Real held-out items in the mode condition"
    )
    max_mode_success: float = Field(
        default=0.50, ge=0.0, le=1.0, description="Target success in the mode at most this"
    )
    min_control_success: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Target success on matched non-mode items at least this",
    )
    min_gap_points: float = Field(
        default=25.0,
        ge=0.0,
        allow_inf_nan=False,
        description="Control minus mode success, percentage points",
    )
    min_sources: int = Field(
        default=2, ge=1, strict=True, description="Independent real sources required"
    )
    alpha: float = Field(
        default=0.01, gt=0.0, lt=1.0, description="Significance of the mode/control difference"
    )
    min_confirmatory_excess_points: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
        description=(
            "Amendment A5: the rate-scale Möbius synergy over the region's injected factors, "
            "from the branch design, must reach this many points. None means not required; the "
            "proof statement sets 25 once the branch design is wired."
        ),
    )
    max_grade: Literal[1, 2] = Field(
        default=2,
        description=(
            "Highest confirmation grade admitted. Grade 1: every factor occurs naturally in a "
            "named corpus or is a deployment condition. Grade 2: some factor is attested in "
            "production and injected on real items. Ungrounded factors are never admitted."
        ),
    )
