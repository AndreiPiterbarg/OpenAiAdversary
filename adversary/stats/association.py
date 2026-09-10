"""Rank association between two per-cell quantities (Amendment A7's regret-versus-excess check)."""

from collections.abc import Sequence

from pydantic import Field
from scipy import stats as sps

from adversary.core.config import FrozenModel


class RankAssociation(FrozenModel):
    """Spearman correlation across cells."""

    n: int
    rho: float
    p_value: float
    threshold: float = Field(description="|rho| below this means the two quantities disagree")

    @property
    def agree(self) -> bool:
        return abs(self.rho) >= self.threshold


def spearman(x: Sequence[float], y: Sequence[float], threshold: float = 0.3) -> RankAssociation:
    """Spearman's rho between paired sequences."""
    if len(x) != len(y):
        raise ValueError("sequences must be paired")
    if len(x) < 3:
        return RankAssociation(
            n=len(x), rho=float("nan"), p_value=float("nan"), threshold=threshold
        )
    result = sps.spearmanr(x, y)
    return RankAssociation(
        n=len(x), rho=float(result.statistic), p_value=float(result.pvalue), threshold=threshold
    )
