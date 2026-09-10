"""The interaction-order curve (R1): what fraction of failure mass is 1-way, 2-way, 3-way.

NIST measured this for conventional software; nobody has for a model. The method mirrors
NIST's attribution: a failing configuration is *explained at order t* if some t-way
combination of its levels fails at a high rate wherever it appears in the sweep, regardless
of the other factors. The curve is the cumulative fraction of failing configurations
explained at each order.

This is an attribution heuristic, not a fitted model. It is transparent and matches the
published curves it will be compared against. A nested-GLM decomposition is the natural
companion and should be added when the first sweep's data exist.
"""

from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode
from adversary.core.factors import Atom, Cell
from adversary.stats.rates import measurable


class InteractionOrderCurve(FrozenModel):
    """Cumulative fraction of failing configurations explained by order <= t."""

    orders: tuple[int, ...]
    cumulative_fraction: tuple[float, ...]
    failing_configurations: int
    unexplained: int = Field(
        description="Failing configurations no combination up to max order explains"
    )
    fail_threshold: float
    min_n: int


def interaction_order_curve(
    episodes: Sequence[Episode],
    max_order: int = 3,
    fail_threshold: float = 0.5,
    min_n: int = 5,
) -> InteractionOrderCurve:
    """Compute the curve from sweep episodes.

    Args:
        episodes: Sweep episodes over full configurations; only measurable ones count.
        max_order: Highest interaction order to attribute.
        fail_threshold: A configuration or combination "fails" if its rate is at least this.
        min_n: Minimum episodes for a configuration or combination to be assessed.
    """
    by_config: dict[Cell, list[bool]] = defaultdict(list)
    for e in measurable(episodes):
        by_config[e.cell].append(e.failed)
    failing = [
        c
        for c, outcomes in by_config.items()
        if len(outcomes) >= min_n and sum(outcomes) / len(outcomes) >= fail_threshold
    ]

    # Failure counts of every combination up to max_order, pooled over all configurations.
    combo_counts: dict[tuple[Atom, ...], list[int]] = defaultdict(lambda: [0, 0])
    for config, outcomes in by_config.items():
        atoms = config.atoms
        failures, n = sum(outcomes), len(outcomes)
        for t in range(1, max_order + 1):
            for group in combinations(atoms, t):
                combo_counts[group][0] += failures
                combo_counts[group][1] += n

    def explains(group: tuple[Atom, ...]) -> bool:
        failures, n = combo_counts[group]
        return n >= min_n and failures / n >= fail_threshold

    explained_at: dict[int, int] = dict.fromkeys(range(1, max_order + 1), 0)
    unexplained = 0
    for config in failing:
        atoms = config.atoms
        order = next(
            (
                t
                for t in range(1, max_order + 1)
                if any(explains(group) for group in combinations(atoms, t))
            ),
            None,
        )
        if order is None:
            unexplained += 1
        else:
            explained_at[order] += 1

    total = len(failing)
    cumulative: list[float] = []
    running = 0
    for t in range(1, max_order + 1):
        running += explained_at[t]
        cumulative.append(running / total if total else float("nan"))
    return InteractionOrderCurve(
        orders=tuple(range(1, max_order + 1)),
        cumulative_fraction=tuple(cumulative),
        failing_configurations=total,
        unexplained=unexplained,
        fail_threshold=fail_threshold,
        min_n=min_n,
    )
