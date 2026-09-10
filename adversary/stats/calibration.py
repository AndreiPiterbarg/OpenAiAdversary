"""Calibrating the instrument before it is allowed to kill anything.

The calibration contract makes a kill conditional on three things:

1. a detectability precondition: the pipeline recovers a planted interaction of reference
   magnitude at >= 80% power, at the seed and cell counts actually used; otherwise the
   experiment is inconclusive, not a kill;
2. a reference magnitude ``delta`` defined by measurement: plant a 3-point interaction on the
   probability scale and record what it reads as under the logistic baseline;
3. equivalence rather than failure to reject: the one-sided upper bound on the central
   estimate of the excess distribution lies below ``delta``.

The pure functions here compute those quantities from measurements the harness and
:mod:`adversary.stats.excess` produce. Running the calibration is an experiment procedure;
these are its arithmetic.
"""

from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.stats.rates import RateEstimate, rate_estimate


def forced_rate_for_excess(natural_rate: float, excess: float) -> float:
    """Forced-failure probability that raises a cell's failure rate by ``excess`` points.

    A planted mode forces failure with probability ``p`` independently of the natural
    outcome, so the resulting rate is ``1 - (1 - p)(1 - q)`` for natural rate ``q``. Solving
    for the target ``q + excess`` gives ``p = excess / (1 - q)``.
    """
    if not 0.0 <= natural_rate < 1.0:
        raise ValueError("natural_rate must be in [0, 1)")
    if excess < 0.0 or natural_rate + excess > 1.0:
        raise ValueError("excess must be non-negative and keep the rate at most 1")
    return excess / (1.0 - natural_rate)


class ReferenceMagnitude(FrozenModel):
    """What a planted probability-scale interaction reads as under the primary baseline."""

    planted_points: float = Field(description="Excess planted on the probability scale, points")
    readings_points: tuple[float, ...] = Field(
        min_length=1, description="Logistic-baseline excess of each planted cell, points"
    )
    delta_points: float = Field(description="Median reading; the reference magnitude")
    ci_low: float
    ci_high: float


def reference_magnitude(
    planted_points: float,
    readings_points: Sequence[float],
    alpha: float = 0.05,
    resamples: int = 2000,
    seed: int = 0,
) -> ReferenceMagnitude:
    """``delta`` as the median reading across planted cells, with a bootstrap interval."""
    values = np.asarray(readings_points, dtype=float)
    if values.size == 0:
        raise ValueError("at least one reading is needed")
    rng = np.random.default_rng(seed)
    medians = np.median(rng.choice(values, size=(resamples, values.size), replace=True), axis=1)
    low, high = (float(x) for x in np.percentile(medians, [100 * alpha / 2, 100 * (1 - alpha / 2)]))
    return ReferenceMagnitude(
        planted_points=planted_points,
        readings_points=tuple(float(v) for v in values),
        delta_points=float(np.median(values)),
        ci_low=low,
        ci_high=high,
    )


class Detectability(FrozenModel):
    """Power of the pipeline to recover planted interactions of reference magnitude."""

    trials: int
    recovered: int
    power: RateEstimate | None = Field(
        description="Recovered over trials, with Wilson interval; unavailable without trials"
    )
    required_power: float
    meets: bool = Field(description="Point estimate reaches the required power")


def detectability(
    recovered_flags: Sequence[bool], required_power: float = 0.8, alpha: float = 0.05
) -> Detectability:
    """Summarise a set of plant-and-recover trials."""
    trials = len(recovered_flags)
    recovered = sum(1 for f in recovered_flags if f)
    power = rate_estimate(recovered, trials, alpha) if trials else None
    return Detectability(
        trials=trials,
        recovered=recovered,
        power=power,
        required_power=required_power,
        meets=bool(power is not None and power.rate >= required_power),
    )


Statistic = Literal["median", "mean"]


class CentralEstimate(FrozenModel):
    """A central statistic of a distribution of cell excesses, with one-sided bounds."""

    statistic: Statistic
    n: int
    point: float
    one_sided_upper: float = Field(description="(1 - alpha) upper bound")
    one_sided_lower: float = Field(description="alpha lower bound")
    alpha: float


def central_estimate(
    values: Sequence[float],
    statistic: Statistic = "median",
    alpha: float = 0.05,
    resamples: int = 2000,
    seed: int = 0,
) -> CentralEstimate:
    """Bootstrap the median or mean of a set of values, resampling the values."""
    array = np.asarray([v for v in values if not np.isnan(v)], dtype=float)
    if array.size == 0:
        raise ValueError("no finite values")
    fn = np.median if statistic == "median" else np.mean
    rng = np.random.default_rng(seed)
    draws = fn(rng.choice(array, size=(resamples, array.size), replace=True), axis=1)
    lower, upper = (float(x) for x in np.percentile(draws, [100 * alpha, 100 * (1 - alpha)]))
    return CentralEstimate(
        statistic=statistic,
        n=int(array.size),
        point=float(fn(array)),
        one_sided_upper=upper,
        one_sided_lower=lower,
        alpha=alpha,
    )


class EquivalenceBelow(FrozenModel):
    """One-sided equivalence: is the estimate demonstrably below a threshold?"""

    upper_bound: float
    threshold: float
    equivalent: bool = Field(description="upper_bound < threshold; a genuine rejection, not a null")


def equivalent_below(upper_bound: float, threshold: float) -> EquivalenceBelow:
    """Declare equivalence only when the one-sided upper bound lies below the threshold."""
    return EquivalenceBelow(
        upper_bound=upper_bound,
        threshold=threshold,
        equivalent=bool(not np.isnan(upper_bound) and upper_bound < threshold),
    )
