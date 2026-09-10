"""Type-I error control across many cells and across a stream of hypotheses.

Supported procedure: Benjamini-Hochberg at q = 0.05 across cells;
sequential testing with Type-I control for the hypothesis stream, because many hypotheses per hot
cell is a multiple-comparisons problem and an uncontrolled kill log is the first thing a reviewer
attacks.
"""

from collections.abc import Callable, Sequence
from math import pi

import numpy as np
from pydantic import Field

from adversary.core.config import FrozenModel


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.05) -> list[bool]:
    """Which hypotheses are rejected at false-discovery rate ``q``."""
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    thresholds = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresholds
    k = int(np.max(np.flatnonzero(passed)) + 1) if passed.any() else 0
    rejected = np.zeros(m, dtype=bool)
    rejected[order[:k]] = True
    return rejected.tolist()


class AlphaSpending(FrozenModel):
    """A fixed spending schedule: test ``k`` gets ``alpha * 6 / (pi^2 k^2)``, summing to ``alpha``.

    Simple, valid for an unbounded stream, and conservative. The e-process below is the less
    conservative alternative when a calibrated e-value is available for each test.
    """

    alpha: float = Field(default=0.05, gt=0, lt=1)

    def level(self, k: int) -> float:
        """Significance level allotted to the ``k``-th test (1-based)."""
        if k < 1:
            raise ValueError("k is 1-based")
        return self.alpha * 6.0 / (pi * pi * k * k)


class EProcess(FrozenModel):
    """Anytime-valid sequential test by multiplying e-values (test martingale).

    Rejects the running null once accumulated evidence reaches ``1 / alpha``. Callers must
    supply e-values from a calibrated construction; this class only aggregates them.
    """

    alpha: float = Field(default=0.05, gt=0, lt=1)
    wealth: float = Field(default=1.0, gt=0)
    updates: int = 0

    def update(self, e_value: float) -> "EProcess":
        """Multiply in one e-value (non-negative, expectation at most 1 under the null)."""
        if e_value < 0:
            raise ValueError("e-values are non-negative")
        return self.model_copy(
            update={"wealth": self.wealth * e_value, "updates": self.updates + 1}
        )

    @property
    def rejects(self) -> bool:
        return self.wealth >= 1.0 / self.alpha


class PermutationNull(FrozenModel):
    """Empirical false-discovery rate of a region-finding procedure under permuted labels."""

    permutations: int
    false_discoveries: int
    rate: float = Field(description="Fraction of permutations in which a region was declared")


def permutation_null(
    labels: Sequence[object],
    outcomes: Sequence[bool],
    finds_region: Callable[[Sequence[object], Sequence[bool]], bool],
    permutations: int = 200,
    seed: int = 0,
) -> PermutationNull:
    """Permute cell labels over episodes and re-run the region procedure (Amendment A8).

    Args:
        labels: Each episode's cell label.
        outcomes: Each episode's failure indicator.
        finds_region: The procedure under test; True when it declares a region.
        permutations: Number of label permutations.
        seed: Permutation seed.
    """
    rng = np.random.default_rng(seed)
    labels_array = np.asarray(labels, dtype=object)
    found = 0
    for _ in range(permutations):
        permuted = labels_array[rng.permutation(len(labels_array))]
        if finds_region(list(permuted), list(outcomes)):
            found += 1
    return PermutationNull(
        permutations=permutations,
        false_discoveries=found,
        rate=found / permutations if permutations else float("nan"),
    )
