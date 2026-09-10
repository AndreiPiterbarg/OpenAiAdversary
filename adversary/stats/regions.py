"""Is a set of hot cells one region or two?

Operational definition: a set of cells is one region iff
their excess values are statistically indistinguishable, tested by a likelihood-ratio test of
a common-excess model against a per-cell-excess model at alpha 0.05. A set that fails is two or
more modes glued together. A chi-square homogeneity test on raw rates is kept for cells without
a fitted prediction.
"""

from collections.abc import Sequence
from math import log

import numpy as np
from pydantic import Field
from scipy import optimize
from scipy import stats as sps

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell

_EPS = 1e-9


class CellCounts(FrozenModel):
    """Failure counts for one cell, with the no-interaction prediction when known."""

    cell: Cell
    n: int = Field(ge=1)
    failures: int = Field(ge=0)
    predicted: float | None = Field(
        default=None, description="Main-effects prediction for this cell"
    )

    @property
    def rate(self) -> float:
        return self.failures / self.n

    @property
    def excess(self) -> float | None:
        return None if self.predicted is None else self.rate - self.predicted


class RegionTest(FrozenModel):
    """Result of a one-region test across cells."""

    method: str
    statistic: float
    p_value: float
    alpha: float
    homogeneous: bool = Field(description="True if the cells are indistinguishable at alpha")
    cells: int
    common_excess: float | None = Field(
        default=None, description="Fitted shared excess under the LRT null"
    )


class Region(FrozenModel):
    """Cells judged to share one failure cause."""

    cells: tuple[Cell, ...]
    n: int
    failures: int

    @property
    def rate(self) -> float:
        return self.failures / self.n if self.n else 0.0

    @property
    def footprint(self) -> Cell:
        """Levels every member shares; the region's name."""
        shared = dict(self.cells[0].levels)
        for c in self.cells[1:]:
            shared = {k: v for k, v in shared.items() if c.levels.get(k) == v}
        return Cell(levels=shared)


def _binom_loglik(k: int, n: int, p: float) -> float:
    p = min(max(p, _EPS), 1 - _EPS)
    return k * log(p) + (n - k) * log(1 - p)


def lrt_common_excess(counts: Sequence[CellCounts], alpha: float = 0.05) -> RegionTest:
    """Likelihood-ratio test: one shared excess over predictions versus a free excess per cell."""
    if len(counts) < 2:
        return RegionTest(
            method="lrt",
            statistic=0.0,
            p_value=1.0,
            alpha=alpha,
            homogeneous=True,
            cells=len(counts),
        )
    if any(c.predicted is None for c in counts):
        raise ValueError(
            "every cell needs a predicted rate for the LRT; use homogeneity() otherwise"
        )

    def neg_common(delta: float) -> float:
        return -sum(_binom_loglik(c.failures, c.n, c.predicted + delta) for c in counts)  # type: ignore[operator]

    fit = optimize.minimize_scalar(neg_common, bounds=(-1.0, 1.0), method="bounded")
    ll_common = -fit.fun
    ll_free = sum(_binom_loglik(c.failures, c.n, c.rate) for c in counts)
    statistic = max(0.0, 2.0 * (ll_free - ll_common))
    p_value = float(sps.chi2.sf(statistic, df=len(counts) - 1))
    return RegionTest(
        method="lrt",
        statistic=float(statistic),
        p_value=p_value,
        alpha=alpha,
        homogeneous=p_value >= alpha,
        cells=len(counts),
        common_excess=float(fit.x),
    )


def homogeneity(counts: Sequence[CellCounts], alpha: float = 0.05) -> RegionTest:
    """Chi-square test that all cells share one failure rate (no prediction needed)."""
    if len(counts) < 2:
        return RegionTest(
            method="chi2",
            statistic=0.0,
            p_value=1.0,
            alpha=alpha,
            homogeneous=True,
            cells=len(counts),
        )
    table = np.array([[c.failures, c.n - c.failures] for c in counts])
    if (table[:, 0] == 0).all() or (table[:, 1] == 0).all():
        return RegionTest(
            method="chi2",
            statistic=0.0,
            p_value=1.0,
            alpha=alpha,
            homogeneous=True,
            cells=len(counts),
        )
    statistic, p_value, _, _ = sps.chi2_contingency(table, correction=False)
    return RegionTest(
        method="chi2",
        statistic=float(statistic),
        p_value=float(p_value),
        alpha=alpha,
        homogeneous=p_value >= alpha,
        cells=len(counts),
    )


def one_region(a: Sequence[CellCounts], b: Sequence[CellCounts], alpha: float = 0.05) -> RegionTest:
    """Whether two groups of cells can be treated as one region; LRT when predictions exist."""
    cells = list(a) + list(b)
    if all(c.predicted is not None for c in cells):
        return lrt_common_excess(cells, alpha)
    return homogeneity(cells, alpha)


def adjacent(a: Cell, b: Cell) -> bool:
    """Cells over the same factors differing in exactly one level."""
    return a.factors == b.factors and sum(1 for k in a.factors if a[k] != b[k]) == 1


def cluster_regions(counts: Sequence[CellCounts], alpha: float = 0.05) -> list[Region]:
    """Greedy agglomeration: merge adjacent cells while the merged set passes the region test."""
    clusters: list[list[CellCounts]] = [[c] for c in sorted(counts, key=lambda c: -c.rate)]
    merged = True
    while merged:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                touching = any(adjacent(x.cell, y.cell) for x in clusters[i] for y in clusters[j])
                if touching and one_region(clusters[i], clusters[j], alpha).homogeneous:
                    clusters[i] = clusters[i] + clusters.pop(j)
                    merged = True
                    break
            if merged:
                break
    return [
        Region(
            cells=tuple(c.cell for c in group),
            n=sum(c.n for c in group),
            failures=sum(c.failures for c in group),
        )
        for group in clusters
    ]
