"""Executable interventions over a declared surface, with explicit ablation switches."""

import random
from abc import ABC, abstractmethod
from typing import Any

from adversary.core.factors import Cell
from adversary.domain.channel import Channel


class Perturbation(ABC):
    """The third probe program. A runtime must confine its capabilities."""

    channel: Channel
    clauses: tuple[str, ...]

    def __init__(self, cell: Cell, seed: int | None = None, **config: Any) -> None:
        if not isinstance(self.channel, Channel):
            raise ValueError("channel must be a Channel")
        if (
            not isinstance(self.clauses, tuple)
            or not self.clauses
            or any(not isinstance(c, str) or not c.strip() for c in self.clauses)
            or len(set(self.clauses)) != len(self.clauses)
        ):
            raise ValueError("clauses must be distinct nonempty names")
        if set(cell.levels) != set(self.clauses):
            raise ValueError("cell must assign every declared clause")
        if any(v not in ("on", "off") for v in cell.levels.values()):
            raise ValueError("clause levels must be on or off")
        self.rng = random.Random(seed)
        self.config = config
        self.cell = cell
        self.active = frozenset(c for c in self.clauses if cell[c] == "on")

    @abstractmethod
    def prepare(self, session: Any, spec: Any) -> None:
        """Prepare through capabilities granted by the runtime for this channel."""

    @abstractmethod
    def observe(self, step: int, tool: str, args: dict[str, Any], result: str) -> str:
        """Return the observation delivered to the target; no forced activation."""

    def close(self) -> None:
        """Release resources owned by the intervention, if any."""
        return None
