"""Unseen-species estimators for the undeclared space, with the validity check that gates them.

Amendment A9: any statement of the form "at least N regions remain" or "the probability that
the next proposal finds a new region is U" is printed only from a sentinel arm, the proposer
with all conditioning removed, because directed search biases every estimator here. The
estimators are the classical ones; the validity check is a within-run prediction test.
"""

from collections.abc import Sequence
from math import log, sqrt

from pydantic import Field

from adversary.core.config import FrozenModel


def good_turing_discovery(f1: int, n: int) -> float:
    """Probability that the next proposal finds a new region: singletons over proposals."""
    return f1 / n if n else float("nan")


def chao1(s_obs: int, f1: int, f2: int) -> float:
    """Chao1 lower bound on the number of regions, from singleton and doubleton counts."""
    if f2 > 0:
        return s_obs + f1 * f1 / (2 * f2)
    return s_obs + f1 * (f1 - 1) / 2  # bias-corrected form when there are no doubletons


def chao2(s_obs: int, q1: int, q2: int, m: int) -> float:
    """Chao2 lower bound from incidence across ``m`` seeds: regions seen in one or two seeds."""
    if m <= 1:
        return float(s_obs)
    factor = (m - 1) / m
    if q2 > 0:
        return s_obs + factor * q1 * q1 / (2 * q2)
    return s_obs + factor * q1 * (q1 - 1) / 2


class SpeciesEstimate(FrozenModel):
    """What the sentinel arm supports saying about the undeclared space."""

    proposals: int
    observed_regions: int
    singletons: int
    doubletons: int
    discovery_probability: float = Field(description="Good-Turing f1/N")
    chao1_lower: float
    chao2_lower: float | None = Field(default=None, description="Across seeds, if more than one")
    extrapolation_limit: int = Field(description="No extrapolation past N log N proposals")
    source: str = Field(default="sentinel", description="Only 'sentinel' estimates may be printed")


def species_estimate(
    proposals: int,
    counts: Sequence[int],
    incidence: Sequence[int] | None = None,
    seeds: int = 1,
    source: str = "sentinel",
) -> SpeciesEstimate:
    """Summarise a proposal stream.

    Args:
        proposals: Number of proposals in the stream.
        counts: Per-region number of proposals that landed in it (abundance).
        incidence: Per-region number of seeds in which it appeared, for Chao2.
        seeds: Number of seeds.
        source: 'sentinel' or 'directed'; directed numbers are diagnostics only.
    """
    f1 = sum(1 for c in counts if c == 1)
    f2 = sum(1 for c in counts if c == 2)
    s_obs = sum(1 for c in counts if c > 0)
    chao2_value = None
    if incidence is not None and seeds > 1:
        q1 = sum(1 for c in incidence if c == 1)
        q2 = sum(1 for c in incidence if c == 2)
        chao2_value = chao2(s_obs, q1, q2, seeds)
    return SpeciesEstimate(
        proposals=proposals,
        observed_regions=s_obs,
        singletons=f1,
        doubletons=f2,
        discovery_probability=good_turing_discovery(f1, proposals),
        chao1_lower=chao1(s_obs, f1, f2),
        chao2_lower=chao2_value,
        extrapolation_limit=int(proposals * log(proposals)) if proposals > 1 else proposals,
        source=source,
    )


class ValidityCheck(FrozenModel):
    """Within-run prediction test: does the first 80% predict the last 20% within a factor of 2?"""

    seeds: int
    passed_seeds: int
    required_seeds: int
    valid: bool


def _predicted_new(first_counts: Sequence[int], first_n: int, later_n: int) -> float:
    """Expected new regions in ``later_n`` proposals from the Good-Turing discovery rate."""
    f1 = sum(1 for c in first_counts if c == 1)
    return later_n * good_turing_discovery(f1, first_n)


def validity_check(
    per_seed_streams: Sequence[Sequence[int]], fraction: float = 0.8, required_seeds: int = 4
) -> ValidityCheck:
    """Per seed, split the stream of region ids at ``fraction``; predict the count of new regions
    in the tail from the head and require the observation within a factor of two of it.

    Args:
        per_seed_streams: For each seed, the region id of each proposal in order (0 for none).
    """
    passed = 0
    for stream in per_seed_streams:
        cut = int(len(stream) * fraction)
        head, tail = list(stream[:cut]), list(stream[cut:])
        seen = {r for r in head if r}
        counts = [head.count(r) for r in seen]
        predicted = _predicted_new(counts, len(head), len(tail))
        observed = len({r for r in tail if r} - seen)
        low, high = predicted / 2, predicted * 2
        if predicted == 0 and observed == 0:
            passed += 1
        elif low <= observed <= high:
            passed += 1
    return ValidityCheck(
        seeds=len(per_seed_streams),
        passed_seeds=passed,
        required_seeds=required_seeds,
        valid=passed >= required_seeds,
    )


def wald_interval(rate: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Simple interval for a discovery probability."""
    if n == 0:
        return (0.0, 1.0)
    half = z * sqrt(rate * (1 - rate) / n)
    return (max(0.0, rate - half), min(1.0, rate + half))
