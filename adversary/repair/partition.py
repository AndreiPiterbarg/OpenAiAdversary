"""Disjointness by construction between what is evaluated and what is trained on."""

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.seeds import SeedRange


class SeedPartition(FrozenModel):
    """Evaluation seeds and repair seeds must not overlap."""

    eval: SeedRange
    fix: SeedRange

    @model_validator(mode="after")
    def _disjoint(self) -> "SeedPartition":
        if not self.eval.disjoint(self.fix):
            raise ValueError("evaluation and fix seed ranges overlap")
        return self


class PoolPartition(FrozenModel):
    """Resource pools (whatever the domain draws instances from) must not overlap."""

    eval_pool: tuple[str, ...] = Field(
        min_length=1, description="Resource ids the evaluation may use"
    )
    fix_pool: tuple[str, ...] = Field(min_length=1, description="Resource ids the repair may use")

    @model_validator(mode="after")
    def _disjoint(self) -> "PoolPartition":
        shared = set(self.eval_pool) & set(self.fix_pool)
        if shared:
            raise ValueError(f"pools overlap: {sorted(shared)}")
        return self
