"""What the search layer is conditioned on. Plain data: the layer runs with or without a sweep."""

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell, FactorSpace
from adversary.stats.excess import ExcessEstimate


class MinedSeed(FrozenModel):
    """Exogenous input with immutable revision addresses, rendered without reinterpretation."""

    instance_id: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    miner: str = Field(min_length=1)
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    ts: int = Field(ge=0)
    subject: str


class EliteSummary(FrozenModel):
    """A compact view of one archive elite for prompting."""

    probe_id: str
    hypothesis: str
    niche: tuple[str, ...]
    score: float


class SearchContext(FrozenModel):
    """Everything a proposer or mutator may look at."""

    space: FactorSpace | None = None
    mined_seed: MinedSeed | None = None
    operator_register: tuple[str, ...] = ()
    hot_cells: tuple[ExcessEstimate, ...] = Field(
        default=(), description="Sweep cells ranked by excess; empty when running without Layer 1"
    )
    elites: tuple[EliteSummary, ...] = Field(default=(), description="Current archive occupants")
    transcripts: tuple[str, ...] = Field(default=(), description="Excerpts of failing trajectories")
    base_cell: Cell | None = Field(
        default=None, description="A full configuration to hold fixed when building minimal pairs"
    )

    def stripped(self) -> "SearchContext":
        """The sentinel view (Amendment A9): no hot cells, no elites, no transcripts."""
        return SearchContext(
            space=self.space,
            base_cell=self.base_cell,
            mined_seed=self.mined_seed,
            operator_register=self.operator_register,
        )
