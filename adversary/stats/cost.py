"""Cost accounting and normalisation across arms (Amendment A10).

Arms are compared at equal compute-seconds, counting builds, reference runs, episodes and
snapshot restores, at fixed concurrency, with identical seeds. Yield-versus-budget curves are
reported per seed rather than a single endpoint. If an arm's language-model spend exceeds a
tenth of its compute dollars, the comparison is re-normalised to dollars and both are
reported. The core calls the unit compute-seconds; a domain may name the same unit after its
own execution environment.
"""

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel, StrictModel
from adversary.core.episode import Episode

Category = Literal["build", "run", "reference", "restore"]


class Prices(StrictModel):
    """What compute and model calls cost."""

    compute_dollars_per_hour: float = Field(gt=0, description="One compute-hour")
    input_dollars_per_million_tokens: float = Field(ge=0)
    output_dollars_per_million_tokens: float = Field(ge=0)


class BudgetLedger(FrozenModel):
    """Seconds and tokens an arm spent, by category."""

    seconds: dict[str, float] = Field(default_factory=dict, description="category -> seconds")
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def compute_seconds(self) -> float:
        return sum(self.seconds.values())

    @property
    def compute_hours(self) -> float:
        return self.compute_seconds / 3600.0

    def add(self, category: Category, seconds: float) -> "BudgetLedger":
        totals = dict(self.seconds)
        totals[category] = totals.get(category, 0.0) + seconds
        return self.model_copy(update={"seconds": totals})

    def add_episode(self, episode: Episode) -> "BudgetLedger":
        ledger = self.add("build", episode.build_seconds).add("run", episode.usage.wall_seconds)
        return ledger.model_copy(
            update={
                "input_tokens": ledger.input_tokens + episode.usage.input_tokens,
                "output_tokens": ledger.output_tokens + episode.usage.output_tokens,
            }
        )

    def dollars(self, prices: Prices) -> "Spend":
        compute = self.compute_hours * prices.compute_dollars_per_hour
        llm = (
            self.input_tokens / 1e6 * prices.input_dollars_per_million_tokens
            + self.output_tokens / 1e6 * prices.output_dollars_per_million_tokens
        )
        return Spend(compute_dollars=compute, llm_dollars=llm)


class Spend(FrozenModel):
    """Dollars by kind, and whether the model spend forces dollar normalisation."""

    compute_dollars: float
    llm_dollars: float
    llm_share_threshold: float = 0.10

    @property
    def total(self) -> float:
        return self.compute_dollars + self.llm_dollars

    @property
    def renormalise_to_dollars(self) -> bool:
        """True if model spend exceeds a tenth of compute spend."""
        return self.llm_dollars > self.llm_share_threshold * self.compute_dollars


def ledger_of(episodes: Iterable[Episode]) -> BudgetLedger:
    """A ledger from a set of episodes (build and run categories)."""
    ledger = BudgetLedger()
    for e in episodes:
        ledger = ledger.add_episode(e)
    return ledger


def compute_hours(episodes: Iterable[Episode]) -> float:
    """Build time plus run time over all episodes, in hours."""
    return ledger_of(episodes).compute_hours


def per_compute_hour(count: int, episodes: Iterable[Episode]) -> float:
    """``count`` (e.g. distinct confirmed regions) divided by the compute-hours spent."""
    hours = compute_hours(episodes)
    return count / hours if hours > 0 else float("nan")


class YieldPoint(FrozenModel):
    """Cumulative yield at a budget."""

    seconds: float
    regions: int


class YieldCurve(FrozenModel):
    """Regions found as a function of compute spent, for one arm and seed."""

    arm: str
    seed: int
    points: tuple[YieldPoint, ...]

    def at(self, seconds: float) -> int:
        """Regions found by the time ``seconds`` had been spent."""
        best = 0
        for p in self.points:
            if p.seconds <= seconds:
                best = max(best, p.regions)
        return best


def yield_curve(arm: str, seed: int, events: Sequence[tuple[float, bool]]) -> YieldCurve:
    """Build a curve from ``(seconds spent so far, found a new region)`` events in order."""
    regions = 0
    points = []
    for seconds, found in events:
        if found:
            regions += 1
        points.append(YieldPoint(seconds=seconds, regions=regions))
    return YieldCurve(arm=arm, seed=seed, points=tuple(points))
