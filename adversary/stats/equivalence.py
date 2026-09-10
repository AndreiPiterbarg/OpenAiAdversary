"""Paired before/after tests for the non-regression proof.

* :func:`tost_paired`: two one-sided tests that the mean paired difference lies within
  ``±margin``. Equivalence is declared when the ``1 - 2*alpha`` interval sits inside the margin.
* :func:`mcnemar_test`: paired binary outcomes, exact.
* :func:`paired_bootstrap`: percentile interval and two-sided p for the mean difference,
  resampling clusters when items are grouped (by source, by task family) so standard errors
  are not understated.
"""

from collections.abc import Sequence

import numpy as np
from pydantic import Field
from scipy import stats as sps
from statsmodels.stats.contingency_tables import mcnemar

from adversary.core.config import FrozenModel


class EquivalenceResult(FrozenModel):
    """TOST outcome on paired scores."""

    n: int
    margin: float
    mean_difference: float = Field(description="after minus before")
    ci_low: float
    ci_high: float
    p_value: float = Field(description="max of the two one-sided p-values")
    equivalent: bool
    alpha: float
    clustered: bool


def _cluster_means(diff: np.ndarray, clusters: Sequence[str] | None) -> np.ndarray:
    if clusters is None:
        return diff
    keys = np.array(clusters)
    return np.array([diff[keys == k].mean() for k in np.unique(keys)])


def tost_paired(
    before: Sequence[float],
    after: Sequence[float],
    margin: float = 0.02,
    alpha: float = 0.05,
    clusters: Sequence[str] | None = None,
) -> EquivalenceResult:
    """Two one-sided tests of |mean(after - before)| < margin.

    With ``clusters``, differences are averaged within cluster first and the test runs on
    cluster means, a conservative treatment of within-cluster correlation.
    """
    b = np.asarray(before, dtype=float)
    a = np.asarray(after, dtype=float)
    if b.shape != a.shape:
        raise ValueError("before and after must be paired")
    diff = _cluster_means(a - b, clusters)
    n = len(diff)
    mean = float(diff.mean())
    se = float(diff.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
    df = n - 1
    if se == 0:
        p_lower = p_upper = 0.0 if abs(mean) < margin else 1.0
    else:
        p_lower = float(1 - sps.t.cdf((mean + margin) / se, df))
        p_upper = float(sps.t.cdf((mean - margin) / se, df))
    p_value = max(p_lower, p_upper)
    t_crit = float(sps.t.ppf(1 - alpha, df)) if df > 0 else float("inf")
    ci_low, ci_high = mean - t_crit * se, mean + t_crit * se
    return EquivalenceResult(
        n=n,
        margin=margin,
        mean_difference=mean,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        equivalent=bool(p_value < alpha),
        alpha=alpha,
        clustered=clusters is not None,
    )


class McNemarResult(FrozenModel):
    """Exact McNemar test on paired binary outcomes."""

    n: int
    before_only: int = Field(description="Passed before, failed after")
    after_only: int = Field(description="Failed before, passed after")
    statistic: float
    p_value: float


def mcnemar_test(before: Sequence[bool], after: Sequence[bool]) -> McNemarResult:
    """Exact McNemar test; ``before``/``after`` are pass indicators per item."""
    b = np.asarray(before, dtype=bool)
    a = np.asarray(after, dtype=bool)
    if b.shape != a.shape:
        raise ValueError("before and after must be paired")
    before_only = int(np.sum(b & ~a))
    after_only = int(np.sum(~b & a))
    table = [[int(np.sum(b & a)), before_only], [after_only, int(np.sum(~b & ~a))]]
    result = mcnemar(table, exact=True)
    return McNemarResult(
        n=len(b),
        before_only=before_only,
        after_only=after_only,
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
    )


class BootstrapResult(FrozenModel):
    """Percentile bootstrap of the mean paired difference."""

    n: int
    resamples: int
    mean_difference: float
    ci_low: float
    ci_high: float
    p_value: float = Field(description="Two-sided, fraction of resamples crossing zero, doubled")
    clustered: bool


def paired_bootstrap(
    before: Sequence[float],
    after: Sequence[float],
    resamples: int = 2000,
    alpha: float = 0.05,
    clusters: Sequence[str] | None = None,
    seed: int = 0,
) -> BootstrapResult:
    """Bootstrap the mean of ``after - before``; resample clusters if given."""
    diff = np.asarray(after, dtype=float) - np.asarray(before, dtype=float)
    rng = np.random.default_rng(seed)
    if clusters is None:
        groups = [diff[i : i + 1] for i in range(len(diff))]
    else:
        keys = np.array(clusters)
        groups = [diff[keys == k] for k in np.unique(keys)]
    means = np.empty(resamples)
    for r in range(resamples):
        picked = rng.integers(0, len(groups), len(groups))
        means[r] = np.concatenate([groups[i] for i in picked]).mean()
    mean = float(diff.mean())
    low, high = (float(x) for x in np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)]))
    crossing = float(min((means <= 0).mean(), (means >= 0).mean()))
    return BootstrapResult(
        n=len(diff),
        resamples=resamples,
        mean_difference=mean,
        ci_low=low,
        ci_high=high,
        p_value=min(1.0, 2 * crossing),
        clustered=clusters is not None,
    )


def paired_binary_equivalence(
    before: Sequence[bool],
    after: Sequence[bool],
    margin: float = 0.02,
    alpha: float = 0.05,
    clusters: Sequence[str] | None = None,
) -> EquivalenceResult:
    """Finite-sample paired bound, including the unobserved-discordance case.

    Independent items use simultaneous exact bounds on the two discordance probabilities.
    Clustered inputs use Hoeffding on independent, equally weighted resource means in [-1,1].
    The latter explicitly changes the estimand from item-weighted to resource-weighted gain.
    """
    if len(before) != len(after) or len(before) == 0 or not 0 < alpha < 1 or not 0 < margin < 1:
        raise ValueError("nonempty complete pairs, valid margin and alpha required")
    if any(value not in (False, True) for value in (*before, *after)):
        raise ValueError("paired binary outcomes must be zero or one")
    if clusters is not None and len(clusters) != len(before):
        raise ValueError("one cluster per pair required")
    diff = _cluster_means(
        np.asarray(after, dtype=float) - np.asarray(before, dtype=float), clusters
    )
    n, mean = len(diff), float(diff.mean())

    def bounds(level: float) -> tuple[float, float]:
        if clusters is not None:
            radius = float(np.sqrt(2 * np.log(2 / level) / n))
            return max(-1.0, mean - radius), min(1.0, mean + radius)
        positive, negative = int(np.sum(diff == 1)), int(np.sum(diff == -1))

        def interval(count: int) -> tuple[float, float]:
            lo = float(sps.beta.ppf(level / 4, count, n - count + 1)) if count else 0.0
            hi = float(sps.beta.ppf(1 - level / 4, count + 1, n - count)) if count < n else 1.0
            return lo, hi

        pl, pu = interval(positive)
        nl, nu = interval(negative)
        return pl - nu, pu - nl

    low, high = bounds(alpha)
    left, right = 1e-12, 1.0 - 1e-12
    for _ in range(45):
        middle = (left + right) / 2
        lo, hi = bounds(middle)
        if lo > -margin and hi < margin:
            right = middle
        else:
            left = middle
    return EquivalenceResult(
        n=n,
        margin=margin,
        mean_difference=mean,
        ci_low=low,
        ci_high=high,
        p_value=right,
        equivalent=low > -margin and high < margin,
        alpha=alpha,
        clustered=clusters is not None,
    )
