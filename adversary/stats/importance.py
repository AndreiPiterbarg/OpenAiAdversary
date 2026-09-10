"""Importance ranking: severity × deployment prevalence × silence × systematicity.

Importance is computed after the search, never inside it. Prevalence comes from outside the
loop, so :class:`PrevalenceEstimate` records where the number came from and treats a
reasoned argument as a weaker source than a measurement. None of the four terms is global
frequency.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell


class PrevalenceEstimate(FrozenModel):
    """How often a region occurs in the customer's deployment, and how we know."""

    value: float = Field(ge=0.0, le=1.0, description="Fraction of deployment traffic in the region")
    source: Literal["customer_traffic", "corpus_measurement", "argument"] = Field(
        description="Measured on customer traffic, measured on a real corpus, or argued"
    )
    notes: str = ""

    @property
    def measured(self) -> bool:
        return self.source != "argument"


class Importance(FrozenModel):
    """The four terms and their product for one region."""

    region: Cell
    severity: float = Field(ge=0.0, description="Points below matched non-region performance")
    prevalence: PrevalenceEstimate
    silence: float = Field(ge=0.0, le=1.0, description="Share of failures reported as successes")
    systematicity: float = Field(ge=0.0, le=1.0, description="Failure rate inside the region")

    @property
    def score(self) -> float:
        return self.severity * self.prevalence.value * self.silence * self.systematicity


def rank(items: Sequence[Importance]) -> list[Importance]:
    """Highest importance first; measured prevalence ranks above argued at equal score."""
    return sorted(items, key=lambda i: (-i.score, not i.prevalence.measured))
