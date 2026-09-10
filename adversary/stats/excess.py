"""Excess over the additive prediction: the adversary's objective.

For a cell ``c``::

    excess(c) = observed_failure_rate(c) - predicted_failure_rate(c)

where the prediction comes from a model with no interaction terms. The default
baseline is :attr:`Baseline.LOGISTIC`: fit a
main-effects-only logistic regression on the sweep episodes; the prediction for a cell is the
mean fitted rate over the episodes covering it; excess is reported on the rate scale with the
odds ratio alongside. Amendment A1 requires all three scales for every cell, so two simpler
baselines are kept:

* ``ADDITIVE``: ``p0 + sum_i (p_i - p0)`` on the probability scale, clipped to [0, 1].
* ``INDEPENDENT``: independent causes (noisy-OR), ``1 - prod_i (1 - p_i)``.

Intervals are a cluster bootstrap: episodes are resampled by ``Episode.resource`` (the pool
member they were drawn from) so many instances from one resource do not masquerade as
independent evidence. Per Amendment A4 the prediction for a reported cell comes from a fit that
excludes that cell's own episodes, so a cell cannot pull its prediction toward itself.
"""

import warnings
from collections.abc import Sequence
from enum import StrEnum

import numpy as np
import statsmodels.api as sm
from pydantic import Field
from scipy.special import expit

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode
from adversary.core.factors import Cell
from adversary.stats.rates import measurable


class ExcessUnavailable(ValueError):
    """The observations do not identify the requested no-interaction prediction."""


class Baseline(StrEnum):
    """How the no-interaction prediction is formed."""

    LOGISTIC = "logistic"
    ADDITIVE = "additive"
    INDEPENDENT = "independent"


class ExcessEstimate(FrozenModel):
    """Observed minus predicted failure rate for one cell, with cluster-bootstrap bounds."""

    cell: Cell
    n: int = Field(ge=0, description="Measurable episodes covering the cell")
    observed: float
    predicted: float = Field(description="No-interaction prediction under ``baseline``")
    excess: float = Field(description="observed - predicted, in probability")
    odds_ratio: float | None = Field(default=None, description="observed odds over predicted odds")
    ci_low: float = Field(description="Two-sided lower bound at alpha")
    ci_high: float = Field(description="Two-sided upper bound at alpha")
    one_sided_upper: float = Field(
        description="One-sided (1 - alpha) upper bound; the quantity an equivalence test compares"
    )
    alpha: float
    baseline: Baseline
    marginals: dict[str, float] = Field(description="'factor=level' -> marginal failure rate")
    clusters: int = Field(description="Distinct resources resampled by the bootstrap")

    @property
    def excess_points(self) -> float:
        """Excess in percentage points."""
        return 100.0 * self.excess


def _design(cells: Sequence[Cell]) -> np.ndarray:
    """One-hot main-effects design with an intercept and reference coding (first level dropped)."""
    factors = sorted({k for c in cells for k in c.factors})
    blocks = [np.ones((len(cells), 1))]
    for factor in factors:
        levels = sorted({c.levels.get(factor, "") for c in cells})
        for level in levels[1:]:
            blocks.append(
                np.array([[1.0 if c.levels.get(factor) == level else 0.0] for c in cells])
            )
    return np.hstack(blocks)


def main_effects_fit(cells: Sequence[Cell], failed: np.ndarray) -> np.ndarray:
    """Fitted failure probabilities from a main-effects-only logistic regression on all rows."""
    everything = np.ones(len(cells), dtype=bool)
    return _fit_predict(_design(cells), failed, everything, everything)


def _fit_predict(
    X: np.ndarray, failed: np.ndarray, fit_mask: np.ndarray, at: np.ndarray
) -> np.ndarray:
    """Fit a main-effects logistic model on ``fit_mask`` rows and predict at ``at`` rows."""
    if not fit_mask.any() or np.any(np.all(X[fit_mask] == 0, axis=0) & np.any(X[at] != 0, axis=0)):
        raise ExcessUnavailable("held-out levels lack baseline support; report the raw contrast")
    projection = X[at] @ np.linalg.pinv(X[fit_mask]) @ X[fit_mask]
    if not np.allclose(projection, X[at], atol=1e-10):
        raise ExcessUnavailable("held-out contrast is not identified by the baseline design")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            result = sm.GLM(failed[fit_mask], X[fit_mask], family=sm.families.Binomial()).fit()
            params = np.asarray(result.params)
            if not np.all(np.isfinite(params)):
                raise ValueError("non-finite fit")
        except Exception:  # noqa: BLE001 - separation or singularity: fall back to a ridge fit
            result = sm.GLM(
                failed[fit_mask], X[fit_mask], family=sm.families.Binomial()
            ).fit_regularized(alpha=1e-3, L1_wt=0.0)
            params = np.asarray(result.params)
    return np.clip(expit(X[at] @ params), 1e-9, 1 - 1e-9)


class _Sample:
    """One (re)sample of episodes with everything the three baselines need."""

    def __init__(
        self, cells: Sequence[Cell], failed: np.ndarray, baseline: Baseline, leave_out: bool
    ) -> None:
        self.cells = cells
        self.failed = failed
        self.baseline = baseline
        self.leave_out = leave_out
        self.X = _design(cells) if baseline is Baseline.LOGISTIC else None
        self._shared: np.ndarray | None = None

    def _fitted_all(self) -> np.ndarray:
        if self._shared is None:
            assert self.X is not None
            everything = np.ones(len(self.cells), dtype=bool)
            self._shared = _fit_predict(self.X, self.failed, everything, everything)
        return self._shared

    def _marginal(self, factor: str, level: str, pool: np.ndarray) -> float:
        mask = pool & np.fromiter((c.levels.get(factor) == level for c in self.cells), dtype=bool)
        return float(self.failed[mask].mean()) if mask.any() else float("nan")

    def observed_and_predicted(self, cell: Cell) -> tuple[float, float, dict[str, float]]:
        covers = np.fromiter((c.covers(cell) for c in self.cells), dtype=bool)
        observed = float(self.failed[covers].mean()) if covers.any() else float("nan")
        # Amendment A4: the prediction for a reported cell excludes that cell's own episodes.
        pool = ~covers if self.leave_out else np.ones(len(self.cells), dtype=bool)
        marginals = {f"{k}={v}": self._marginal(k, v, pool) for k, v in cell.items()}
        if not covers.any():
            return observed, float("nan"), marginals
        if not pool.any():
            raise ExcessUnavailable("no independent rows remain for the additive baseline")
        if self.baseline is Baseline.LOGISTIC:
            assert self.X is not None
            if self.leave_out:
                predicted = float(_fit_predict(self.X, self.failed, pool, covers).mean())
            else:
                predicted = float(self._fitted_all()[covers].mean())
        elif self.baseline is Baseline.ADDITIVE:
            grand = float(self.failed[pool].mean())
            predicted = float(np.clip(grand + sum(m - grand for m in marginals.values()), 0.0, 1.0))
        else:
            predicted = float(1.0 - np.prod([1.0 - m for m in marginals.values()]))
        return observed, predicted, marginals


def _empty(cell: Cell, baseline: Baseline, alpha: float) -> ExcessEstimate:
    nan = float("nan")
    return ExcessEstimate(
        cell=cell,
        n=0,
        observed=nan,
        predicted=nan,
        excess=nan,
        ci_low=nan,
        ci_high=nan,
        one_sided_upper=nan,
        alpha=alpha,
        baseline=baseline,
        marginals={},
        clusters=0,
    )


def estimate_excess(
    episodes: Sequence[Episode],
    cells: Sequence[Cell],
    baseline: Baseline = Baseline.LOGISTIC,
    bootstrap: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
    leave_cell_out: bool = True,
) -> list[ExcessEstimate]:
    """Estimate the interaction excess of several cells from the same sweep episodes.

    Args:
        episodes: All sweep episodes; the baseline is fitted on measurable ones. Planted and
            unrealised episodes are excluded automatically.
        cells: The partial configurations whose interaction is being measured.
        baseline: Prediction rule; the pre-registered default is ``LOGISTIC``.
        bootstrap: Cluster-bootstrap resamples for the intervals; ``0`` disables.
        alpha: Level for the two-sided interval and the one-sided upper bound.
        seed: Bootstrap seed.
        leave_cell_out: Amendment A4: predict each cell from a fit that excludes its own
            episodes, so a cell cannot pull its prediction toward itself. ``False`` shares one
            fit across cells, which is faster and slightly biased toward zero excess.

    Returns:
        One estimate per cell, in the order given.
    """
    rows = measurable(episodes)
    if not rows or not cells:
        return [_empty(c, baseline, alpha) for c in cells]
    all_cells = [e.cell for e in rows]
    if len({tuple(sorted(c.factors)) for c in all_cells}) > 1:
        raise ExcessUnavailable("incompatible clause bases; report paired contrast and control")
    failed = np.fromiter((e.failed for e in rows), dtype=float)
    clusters = np.array([e.resource or e.id for e in rows])
    groups = [np.flatnonzero(clusters == g) for g in np.unique(clusters)]

    full = _Sample(all_cells, failed, baseline, leave_cell_out)
    points = [full.observed_and_predicted(c) for c in cells]
    draws: list[list[float]] = [[] for _ in cells]
    if bootstrap:
        rng = np.random.default_rng(seed)
        for _ in range(bootstrap):
            idx = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
            sample = _Sample([all_cells[i] for i in idx], failed[idx], baseline, leave_cell_out)
            for k, cell in enumerate(cells):
                try:
                    o, p, _ = sample.observed_and_predicted(cell)
                except ExcessUnavailable:
                    continue
                if np.isfinite(o) and np.isfinite(p):
                    draws[k].append(o - p)

    estimates: list[ExcessEstimate] = []
    for k, cell in enumerate(cells):
        observed, predicted, marginals = points[k]
        excess = observed - predicted
        odds_ratio = None
        if 0 < observed < 1 and 0 < predicted < 1:
            odds_ratio = (observed / (1 - observed)) / (predicted / (1 - predicted))
        low = high = upper = float("nan")
        if bootstrap and len(draws[k]) < max(2, bootstrap // 2):
            raise ExcessUnavailable("too few identifiable bootstrap draws for an excess interval")
        if draws[k]:
            low, high, upper = (
                float(x)
                for x in np.percentile(
                    draws[k], [100 * alpha / 2, 100 * (1 - alpha / 2), 100 * (1 - alpha)]
                )
            )
        estimates.append(
            ExcessEstimate(
                cell=cell,
                n=int(sum(1 for c in all_cells if c.covers(cell))),
                observed=observed,
                predicted=predicted,
                excess=excess,
                odds_ratio=odds_ratio,
                ci_low=low,
                ci_high=high,
                one_sided_upper=upper,
                alpha=alpha,
                baseline=baseline,
                marginals=marginals,
                clusters=len(groups),
            )
        )
    return estimates


def excess_over_additive(
    episodes: Sequence[Episode],
    cell: Cell,
    baseline: Baseline = Baseline.LOGISTIC,
    bootstrap: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
    leave_cell_out: bool = True,
) -> ExcessEstimate:
    """:func:`estimate_excess` for a single cell."""
    return estimate_excess(episodes, [cell], baseline, bootstrap, alpha, seed, leave_cell_out)[0]


def hot_cells(
    episodes: Sequence[Episode],
    candidates: Sequence[Cell],
    min_n: int = 5,
    baseline: Baseline = Baseline.LOGISTIC,
    bootstrap: int = 200,
    seed: int = 0,
    leave_cell_out: bool = True,
) -> list[ExcessEstimate]:
    """Rank candidate cells by excess, dropping those with too few covering episodes."""
    estimates = estimate_excess(
        episodes, list(candidates), baseline, bootstrap, seed=seed, leave_cell_out=leave_cell_out
    )
    return sorted((e for e in estimates if e.n >= min_n), key=lambda e: -e.excess)
