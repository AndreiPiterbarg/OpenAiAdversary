"""Failure rates, intervals and two-arm comparisons over episodes.

Everything here takes plain numbers or :class:`~adversary.core.episode.Episode` sequences
and returns frozen results. No model, no environment. :func:`measurable` is the one
definition of which episodes count toward a cell statistic.
"""

from collections.abc import Iterable, Sequence
from math import isfinite, sqrt

from pydantic import Field, model_validator
from scipy import stats as sps

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode
from adversary.core.factors import Cell


def measurable(episodes: Iterable[Episode]) -> list[Episode]:
    """Episodes that measure their cell: realised, and not forced by a planted mode."""
    return [e for e in episodes if e.measurable]


class RateEstimate(FrozenModel):
    """A binomial proportion with a Wilson interval."""

    n: int = Field(gt=0, strict=True)
    successes: int = Field(ge=0, strict=True, description="Count of the event being estimated")
    rate: float = Field(ge=0, le=1, strict=True)
    ci_low: float = Field(ge=0, le=1, strict=True)
    ci_high: float = Field(ge=0, le=1, strict=True)
    alpha: float = Field(default=0.05, gt=0, lt=1, strict=True)

    @model_validator(mode="after")
    def consistent(self) -> "RateEstimate":
        _validate_counts(self.successes, self.n)
        if self.rate != self.successes / self.n:
            raise ValueError("rate must equal successes / n")
        if not self.ci_low <= self.rate <= self.ci_high:
            raise ValueError("interval must contain the estimated rate")
        return self


def _validate_counts(successes: int, n: int) -> None:
    if type(n) is not int or type(successes) is not int:
        raise ValueError("counts must be integers, not booleans or coerced values")
    if n < 0 or not 0 <= successes <= n:
        raise ValueError("counts require 0 <= successes <= n")
    if n == 0:
        raise ValueError("rate unavailable: no measurable observations (n=0)")


def _validate_alpha(alpha: float) -> None:
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
        raise ValueError("alpha must be a finite number strictly between 0 and 1")
    if not isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be a finite number strictly between 0 and 1")


def wilson_interval(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a proportion; well behaved at 0 and 1."""
    _validate_counts(successes, n)
    _validate_alpha(alpha)
    z = float(sps.norm.isf(alpha / 2))
    if not isfinite(z):
        raise ValueError("alpha is too small for a finite interval")
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (
        0.0 if successes == 0 else max(0.0, centre - half),
        1.0 if successes == n else min(1.0, centre + half),
    )


def rate_estimate(successes: int, n: int, alpha: float = 0.05) -> RateEstimate:
    """Build a :class:`RateEstimate`; refuse an empty or invalid denominator."""
    low, high = wilson_interval(successes, n, alpha)
    return RateEstimate(
        n=n,
        successes=successes,
        rate=successes / n,
        ci_low=low,
        ci_high=high,
        alpha=alpha,
    )


def failure_rate(episodes: Iterable[Episode], alpha: float = 0.05) -> RateEstimate:
    """Failure proportion with interval, over measurable episodes."""
    rows = measurable(episodes)
    return rate_estimate(sum(1 for e in rows if e.failed), len(rows), alpha)


def in_cell(episodes: Iterable[Episode], cell: Cell) -> list[Episode]:
    """Episodes whose configuration covers ``cell``."""
    return [e for e in episodes if e.cell.covers(cell)]


class Comparison(FrozenModel):
    """Independent-arm difference; not a task-grouped or paired inference."""

    control: RateEstimate
    treatment: RateEstimate
    effect: float = Field(
        ge=-1, le=1, strict=True, description="treatment rate minus control rate, in probability"
    )
    ci_low: float = Field(ge=-1, le=1, strict=True)
    ci_high: float = Field(ge=-1, le=1, strict=True)
    p_value: float = Field(
        ge=0, le=1, strict=True, description="Fisher exact, two-sided, independent counts"
    )

    @model_validator(mode="after")
    def consistent(self) -> "Comparison":
        if self.control.alpha != self.treatment.alpha:
            raise ValueError("both arms require the same alpha")
        if self.effect != self.treatment.rate - self.control.rate:
            raise ValueError("effect must equal treatment rate minus control rate")
        if not self.ci_low <= self.effect <= self.ci_high:
            raise ValueError("interval must contain the estimated effect")
        return self


def compare_rates(
    control_failures: int,
    control_n: int,
    treatment_failures: int,
    treatment_n: int,
    alpha: float = 0.05,
) -> Comparison:
    """Fisher exact test and Newcombe's Wilson interval for independent arms.

    Refuses missing denominators. The interval avoids the Wald zero-width failure
    at boundary proportions. Neither this interval nor Fisher accounts for shared
    tasks, paired seeds or selection; formal grouped confirmation belongs elsewhere.
    """
    control = rate_estimate(control_failures, control_n, alpha)
    treatment = rate_estimate(treatment_failures, treatment_n, alpha)
    table = [
        [treatment_failures, treatment_n - treatment_failures],
        [control_failures, control_n - control_failures],
    ]
    _, p_value = sps.fisher_exact(table)
    effect = treatment.rate - control.rate
    lower_distance = sqrt(
        (treatment.rate - treatment.ci_low) ** 2 + (control.ci_high - control.rate) ** 2
    )
    upper_distance = sqrt(
        (treatment.ci_high - treatment.rate) ** 2 + (control.rate - control.ci_low) ** 2
    )
    return Comparison(
        control=control,
        treatment=treatment,
        effect=effect,
        ci_low=max(-1.0, effect - lower_distance),
        ci_high=min(1.0, effect + upper_distance),
        p_value=float(p_value),
    )


def compare_arms(
    control: Sequence[Episode], treatment: Sequence[Episode], alpha: float = 0.05
) -> Comparison:
    """:func:`compare_rates` over two episode sequences (measurable episodes only)."""
    c, t = measurable(control), measurable(treatment)
    return compare_rates(
        sum(1 for e in c if e.failed), len(c), sum(1 for e in t if e.failed), len(t), alpha
    )


def zero_failure_bound(n: int, detection_rate: float) -> float:
    """Upper bound on the failure rate compatible with zero observed failures.

    The rule of three, corrected for the pipeline's own detection rate ``d``: with ``n``
    episodes and no failures, the rate is below ``3 / (n * d)`` at roughly 95% confidence
    (Amendment A8). Reported per cell so "every cell's result" is not read as a proof of
    absence.
    """
    if type(n) is not int or n < 0:
        raise ValueError("n must be a non-negative integer")
    if (
        isinstance(detection_rate, bool)
        or not isinstance(detection_rate, (int, float))
        or not isfinite(detection_rate)
        or not 0 <= detection_rate <= 1
    ):
        raise ValueError("detection_rate must be a finite probability")
    if n == 0 or detection_rate == 0:
        return 1.0
    return min(1.0, 3.0 / (n * detection_rate))
