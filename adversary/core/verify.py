"""Verdicts and the verifier contract.

A verifier is code. It receives the trajectory the target produced and the instance's
hidden oracle and returns a :class:`Verdict`. It may combine several named oracles
(``channels``), and the verdict passes only if every channel passes. Verifiers must not consult
a language model; the loader in
``adversary.probe.program`` refuses verifier programs that import the model boundary.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.trajectory import Trajectory


class Verdict(FrozenModel):
    """Outcome of verifying one trajectory."""

    passed: bool = Field(description="Overall pass; equals all(channels) when channels are given")
    channels: dict[str, bool] = Field(
        default_factory=dict,
        description="Named independent oracles, e.g. {'tests': True, 'state': False}",
    )
    notes: str = Field(default="", description="Free-text diagnostics for the audit trail")

    @model_validator(mode="after")
    def _passed_matches_channels(self) -> "Verdict":
        if self.channels and self.passed != all(self.channels.values()):
            raise ValueError("passed must equal all(channels.values()) when channels are given")
        return self

    @classmethod
    def from_channels(cls, notes: str = "", **channels: bool) -> "Verdict":
        """Build a verdict whose ``passed`` is derived from the channels."""
        return cls(passed=all(channels.values()), channels=dict(channels), notes=notes)


class Verifier(ABC):
    """Code that decides pass or fail. Never a model."""

    version: str = "0"
    """Bumped whenever a verdict could change for a fixed (trajectory, oracle)."""

    @abstractmethod
    def verify(self, trajectory: Trajectory, oracle: Any) -> Verdict:
        """Score one trajectory against the instance's oracle.

        Args:
            trajectory: What the target did, including the environment's final state.
            oracle: The instance's hidden ground truth.

        Returns:
            A verdict; ``channels`` should name each independent oracle consulted.
        """

    @property
    def identity(self) -> str:
        """``module:Class`` string recorded in provenance."""
        return f"{type(self).__module__}:{type(self).__qualname__}"
