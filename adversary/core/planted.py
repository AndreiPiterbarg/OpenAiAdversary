"""Planted modes: known failures injected into a run to measure our own false-negative rate.

A coverage argument says what was tested, not whether a failure in a visited cell would have
been recognised. Following the hidden-objective audit protocol, a :class:`PlantedMode` forces
failures in a named cell; the harness marks every affected episode ``planted=True`` so audit
runs can never be mistaken for measurements, and :mod:`adversary.protocol.planted` measures
whether the pipeline found what was planted.
"""

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.util import sha256_text


class PlantedMode(FrozenModel):
    """A failure region we know is there because we put it there."""

    id: str
    cell: Cell = Field(description="Region in which failures are forced")
    failure_rate: float = Field(
        ge=0.0, le=1.0, description="Forced failure probability inside the region"
    )
    silent: bool = Field(default=True, description="Whether the forced failure also claims success")

    def fires(self, instance_id: str) -> bool:
        """Deterministic per instance so re-runs agree."""
        draw = int(sha256_text(f"{self.id}:{instance_id}")[:8], 16) / 0xFFFFFFFF
        return draw < self.failure_rate
