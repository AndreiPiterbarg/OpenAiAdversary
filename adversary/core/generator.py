"""Abstract base class for deterministic instance generators.

A generator is an infinite, seed-deterministic iterator of :class:`Instance` objects for one
factor cell. The plugin's environment builder supplies one per swept cell; a probe's ``gen``
program is one too. Determinism given ``seed`` is a contract, not a courtesy: the repair
layer relies on disjoint seed ranges producing disjoint data.
"""

import random
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from adversary.core.factors import Cell
from adversary.core.instance import Instance


class Generator(ABC):
    """Infinite iterator of instances realising one cell."""

    version: str = "0"
    """Bumped whenever generated content changes for a fixed seed."""

    def __init__(self, cell: Cell, seed: int | None = None, **config: Any) -> None:
        """Initialise the generator.

        Args:
            cell: The full configuration every emitted instance must realise.
            seed: Seed for the private random stream. ``None`` means non-reproducible.
            **config: Generator-specific parameters, validated by the subclass.
        """
        self.cell = cell
        self.seed = seed
        self.config = config
        self.rng = random.Random(seed)

    def __iter__(self) -> Iterator[Instance]:
        return self

    @abstractmethod
    def __next__(self) -> Instance:
        """Emit the next instance. Never terminates; the caller decides how many to draw."""

    def generate_batch(self, n: int) -> list[Instance]:
        """Draw ``n`` instances."""
        return [next(self) for _ in range(n)]

    def next_seed(self) -> int:
        """Draw a per-instance seed from the private stream."""
        return self.rng.getrandbits(63)

    @property
    def identity(self) -> str:
        """``module:Class`` string recorded in provenance."""
        return f"{type(self).__module__}:{type(self).__qualname__}"
