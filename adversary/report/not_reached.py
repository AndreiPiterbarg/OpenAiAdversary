"""The explicit statement of what was not reached. Derived, never hand-written.

A coverage claim is credible because of its gaps. This module assembles them from the
measurements: realisable combinations never executed (with the subset the run's own
constraints blocked), instances that produced no episode by stage, episodes whose
perturbation never applied, combinations excluded by declaration, combinations infeasible by
implication (a finding for the factor-space audit), factors held constant, factors that
discretise a continuum, and probes whose regions lie outside the swept envelope.
"""

from collections import Counter
from collections.abc import Iterable

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode, Stage, Unreached
from adversary.core.factors import Cell, FactorSpace
from adversary.probe.probe import Probe


class UnreachedSummary(FrozenModel):
    """How many instances of one configuration stopped at one stage."""

    cell: Cell
    stage: Stage
    count: int


class NotReached(FrozenModel):
    """Everything the claim does not cover, by cause."""

    unreached: tuple[UnreachedSummary, ...] = Field(
        description="Instances that produced no episode, by configuration and stage"
    )
    unrealised_episodes: int = Field(
        description="Episodes whose scheduled perturbation never applied; excluded from cells"
    )
    pinned: Cell = Field(description="Factors held constant in every configuration")
    discretised: tuple[str, ...] = Field(
        description="Factors standing in for a continuous quantity"
    )
    outside_envelope: tuple[str, ...] = Field(
        description="Probe ids whose region uses a factor or level the swept envelope lacks"
    )

    @property
    def empty(self) -> bool:
        """True only if nothing was left out; a report where this is True should be doubted."""
        return (
            not self.unreached
            and not self.unrealised_episodes
            and not self.pinned.levels
            and not self.discretised
            and not self.outside_envelope
        )


def derive_not_reached(
    space: FactorSpace,
    unreached: Iterable[Unreached],
    episodes: Iterable[Episode] = (),
    probes: Iterable[Probe] = (),
) -> NotReached:
    """Assemble the not-reached statement from measurements."""
    counts = Counter((u.cell, u.stage) for u in unreached)
    return NotReached(
        unreached=tuple(
            UnreachedSummary(cell=cell, stage=stage, count=n)
            for (cell, stage), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][1]))
        ),
        unrealised_episodes=sum(1 for e in episodes if not e.realised),
        pinned=space.pinned_cell,
        discretised=tuple(f.name for f in space.factors if f.discretisation_of),
        outside_envelope=tuple(p.id for p in probes if not space.contains(p.cell)),
    )
