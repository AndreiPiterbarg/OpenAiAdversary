"""Seed ranges: the mechanism that keeps evaluation and repair data disjoint by construction."""

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel


class SeedRange(FrozenModel):
    """Half-open integer range ``[start, stop)`` of seeds."""

    start: int = Field(ge=0)
    stop: int = Field(gt=0)

    @model_validator(mode="after")
    def _non_empty(self) -> "SeedRange":
        if self.stop <= self.start:
            raise ValueError(f"empty seed range [{self.start}, {self.stop})")
        return self

    def __len__(self) -> int:
        return self.stop - self.start

    def __contains__(self, seed: object) -> bool:
        return isinstance(seed, int) and self.start <= seed < self.stop

    def at(self, index: int) -> int:
        """The ``index``-th seed; raises if out of range."""
        seed = self.start + index
        if seed not in self:
            raise IndexError(f"index {index} outside seed range of length {len(self)}")
        return seed

    def disjoint(self, other: "SeedRange") -> bool:
        """True if the two ranges share no seed."""
        return self.stop <= other.start or other.stop <= self.start
