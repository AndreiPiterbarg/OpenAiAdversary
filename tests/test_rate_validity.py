"""Refuse missing measurements and retain uncertainty at probability boundaries."""

import math

import pytest
from pydantic import ValidationError
from statsmodels.stats.proportion import confint_proportions_2indep

from adversary.stats.rates import (
    Comparison,
    RateEstimate,
    compare_rates,
    failure_rate,
    rate_estimate,
    wilson_interval,
    zero_failure_bound,
)


@pytest.mark.parametrize(
    "counts", [(0, 0), (-1, 10), (11, 10), (0, -1), (True, 10), (1, True), (1.0, 10), (1, "10")]
)
def test_invalid_or_empty_counts_refused(counts):
    for estimator in (rate_estimate, wilson_interval):
        with pytest.raises(ValueError):
            estimator(*counts)


@pytest.mark.parametrize("alpha", [0, 1, -0.1, 1.1, math.nan, math.inf, True, "0.05"])
def test_invalid_alpha_refused(alpha):
    with pytest.raises(ValueError):
        rate_estimate(1, 10, alpha)


def test_empty_measurement_is_not_a_zero_failure_rate():
    with pytest.raises(ValueError, match="no measurable observations"):
        failure_rate([])
    for counts in [(0, 0, 1, 10), (1, 10, 0, 0), (0, 0, 0, 0)]:
        with pytest.raises(ValueError, match="no measurable observations"):
            compare_rates(*counts)
    assert rate_estimate(0, 10).rate == 0


@pytest.mark.parametrize(
    "counts", [(0, 10, 0, 10), (10, 10, 10, 10), (0, 10, 10, 10), (10, 10, 0, 10), (2, 7, 8, 13)]
)
def test_newcombe_interval_against_independent_library(counts):
    cf, cn, tf, tn = counts
    result = compare_rates(*counts)
    expected = confint_proportions_2indep(tf, tn, cf, cn, method="newcomb", compare="diff")
    assert (result.ci_low, result.ci_high) == pytest.approx(expected)
    assert -1 <= result.ci_low < result.ci_high <= 1
    assert result.ci_low <= result.effect <= result.ci_high
    reverse = compare_rates(tf, tn, cf, cn)
    assert reverse.effect == -result.effect
    assert reverse.ci_low == pytest.approx(-result.ci_high)
    assert reverse.ci_high == pytest.approx(-result.ci_low)
    assert reverse.p_value == pytest.approx(result.p_value)


def test_tiny_alpha_uses_survival_quantile_without_rounding_to_one():
    result = rate_estimate(1, 10, 1e-30)
    assert math.isfinite(result.ci_low) and math.isfinite(result.ci_high)


@pytest.mark.parametrize(
    "update",
    [
        dict(n=0),
        dict(successes=11),
        dict(n=True),
        dict(rate=0.8),
        dict(ci_low=0.5),
        dict(alpha=math.nan),
        dict(ci_high=math.inf),
    ],
)
def test_result_constructor_rejects_impossible_rate_records(update):
    data = rate_estimate(1, 10).model_dump()
    data.update(update)
    with pytest.raises(ValidationError):
        RateEstimate(**data)


@pytest.mark.parametrize(
    "update", [dict(effect=math.nan), dict(effect=0.9), dict(ci_low=0.9), dict(p_value=1.1)]
)
def test_comparison_constructor_rejects_impossible_records(update):
    data = compare_rates(1, 10, 5, 10).model_dump()
    data.update(update)
    with pytest.raises(ValidationError):
        Comparison(**data)


@pytest.mark.parametrize(
    "n,detection",
    [
        (-1, 0.5),
        (True, 0.5),
        (1.0, 0.5),
        (10, -1),
        (10, 1.1),
        (10, math.nan),
        (10, math.inf),
        (10, True),
    ],
)
def test_invalid_zero_failure_bounds_refused(n, detection):
    with pytest.raises(ValueError):
        zero_failure_bound(n, detection)


def test_uninformative_zero_failure_bound_is_one():
    assert zero_failure_bound(0, 0.9) == 1
    assert zero_failure_bound(10, 0) == 1
    assert zero_failure_bound(100, 0.5) == pytest.approx(0.06)


def test_wilson_boundary_endpoints_are_exact_despite_roundoff():
    for n in range(1, 101):
        for alpha in (0.01, 0.05, 0.5):
            assert rate_estimate(n, n, alpha).ci_high == 1
            assert rate_estimate(0, n, alpha).ci_low == 0


def test_empty_calibration_refuses_a_power_measurement():
    from adversary.stats.calibration import detectability

    result = detectability([])
    assert result.power is None
    assert result.trials == 0 and result.recovered == 0
    assert result.meets is False
