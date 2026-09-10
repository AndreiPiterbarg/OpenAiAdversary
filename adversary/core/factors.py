"""The declared operating envelope: factors, levels, cells and the factor space.

These are the vocabulary of the whole system. A :class:`Factor` is one axis of variation
with named discrete levels and a grounding category. A :class:`Cell` is an assignment of
levels to some factors; it is used both for covering-array rows (every varied factor
assigned) and for the partial assignments that name a t-way combination or a failure
region. A :class:`FactorSpace` is the full declaration, including infeasible combinations,
and it fingerprints itself so a coverage claim can name exactly what it covered.

Three distinct reasons a t-way combination is not in a coverage denominator, kept apart
because conflating them misstates the claim:

* *excluded by declaration*: the combination itself completes a declared exclusion;
* *implied-infeasible*: no exclusion forbids it, yet no full configuration can realise it,
  because its levels jointly rule out every level of some other factor (:meth:`is_realisable`);
* *not reached*: realisable, but never executed.

Nothing here knows what a factor *means*. Domain plugins declare the space in YAML.
"""

from collections.abc import Iterator, Mapping
from enum import StrEnum
from functools import cached_property
from itertools import combinations, product
from math import prod
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import Field, field_validator, model_validator

from adversary.core.config import FrozenModel
from adversary.core.util import sha256_json

if TYPE_CHECKING:
    from adversary.core.constraints import Forbidden

Atom = tuple[str, str]
"""One ``(factor, level)`` assignment."""


class Grounding(StrEnum):
    """How a factor's effect can be confirmed on real data.

    A finding is not a mode until it reproduces on real data, so a region's grounding
    decides both whether it can ever be claimed and at what grade.
    """

    CONFIRMABLE = "confirmable"
    """(A) Occurs naturally in a named corpus and is detectable by code. Grade 1."""

    CONDITION = "condition"
    """(A-cond) A deployment or harness setting with a documented production default, applied to
    real tasks without fabricating an event. Grade 1, but carries no discovery about the world
    and is counted separately."""

    ATTESTABLE = "attestable"
    """(B) Attested in production but not runnable against a corpus; realised by injection on
    real items. Grade 2."""

    UNGROUNDED = "ungrounded"
    """(C) No real-world trace. Swept for environment variation only; never in a claimed mode."""


GRADE_1 = frozenset({Grounding.CONFIRMABLE, Grounding.CONDITION})


class Factor(FrozenModel):
    """One axis of the operating envelope with a finite set of named levels."""

    name: str = Field(description="Unique identifier used as the key in every Cell")
    levels: tuple[str, ...] = Field(
        description="Named discrete levels; order is the declared order"
    )
    family: str = Field(
        default="",
        description=(
            "Source of cause this factor belongs to. Interactions across families are the "
            "signal the thesis is about, so the grouping is declared, not inferred."
        ),
    )
    kind: str = Field(
        default="",
        description=(
            "How the factor acts: 'event' (happens mid-episode), 'cond' (a harness or "
            "deployment setting), 'prop' (a property of the task or its source) or 'derived'."
        ),
    )
    description: str = Field(default="", description="Human-readable meaning of the factor")
    pinned: str | None = Field(
        default=None,
        description=(
            "If set, the factor is declared but held at this level in every generated cell. "
            "Used for controlled axes such as a contamination axis that is never varied."
        ),
    )
    discretisation_of: str | None = Field(
        default=None,
        description=(
            "If the factor discretises a continuous quantity, name it here. The report lists "
            "these because a failure can hide between the chosen levels."
        ),
    )
    grounding: Grounding = Field(
        default=Grounding.CONFIRMABLE,
        description=(
            "Grounding category. Regions containing an ungrounded factor are swept but can "
            "never be claimed as modes; an attestable factor caps the mode at grade 2."
        ),
    )
    grounding_note: str = Field(
        default="",
        description="Which corpus or production signal grounds the factor, or why none does",
    )

    @field_validator("levels")
    @classmethod
    def _levels_are_distinct(cls, levels: tuple[str, ...]) -> tuple[str, ...]:
        if len(levels) < 2:
            raise ValueError("a factor needs at least two levels")
        if len(set(levels)) != len(levels):
            raise ValueError(f"duplicate levels: {levels}")
        return levels

    @model_validator(mode="after")
    def _pinned_is_a_level(self) -> "Factor":
        if self.pinned is not None and self.pinned not in self.levels:
            raise ValueError(f"pinned level {self.pinned!r} is not a level of {self.name!r}")
        return self

    @property
    def varied(self) -> bool:
        """Whether this factor is swept (``True``) or held constant (``False``)."""
        return self.pinned is None


class Cell(FrozenModel):
    """An assignment of levels to a subset of factors.

    A cell of order ``t`` names a t-way combination. A cell assigning every varied factor is
    a full configuration, i.e. one row of a covering array. Equality and hashing are by
    content so cells can be set members and dictionary keys.
    """

    levels: dict[str, str] = Field(description="Factor name to level")

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.levels.items())))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Cell) and self.levels == other.levels

    def __getitem__(self, factor: str) -> str:
        return self.levels[factor]

    def __contains__(self, factor: object) -> bool:
        return factor in self.levels

    def __len__(self) -> int:
        return len(self.levels)

    def items(self) -> Iterator[Atom]:
        """Iterate ``(factor, level)`` pairs in factor-name order."""
        return iter(sorted(self.levels.items()))

    @property
    def atoms(self) -> tuple[Atom, ...]:
        """The assignments as a sorted tuple; the canonical key of this cell."""
        return tuple(sorted(self.levels.items()))

    @property
    def order(self) -> int:
        """Number of factors assigned; the ``t`` of a t-way combination."""
        return len(self.levels)

    @property
    def factors(self) -> tuple[str, ...]:
        """Assigned factor names, sorted."""
        return tuple(sorted(self.levels))

    def covers(self, other: "Cell") -> bool:
        """True if every assignment in ``other`` is also made, identically, in this cell."""
        return all(self.levels.get(k) == v for k, v in other.levels.items())

    def project(self, factors: Mapping[str, Any] | tuple[str, ...] | list[str]) -> "Cell":
        """Restrict to the given factors (those present in this cell)."""
        names = factors.keys() if isinstance(factors, Mapping) else factors
        return Cell(levels={k: self.levels[k] for k in names if k in self.levels})

    def merge(self, other: "Cell") -> "Cell":
        """Union of two cells; raises if they disagree on a shared factor."""
        merged = dict(self.levels)
        for k, v in other.levels.items():
            if k in merged and merged[k] != v:
                raise ValueError(f"cells disagree on {k!r}: {merged[k]!r} vs {v!r}")
            merged[k] = v
        return Cell(levels=merged)

    def label(self) -> str:
        """Compact ``factor=level`` rendering, stable across runs."""
        return ",".join(f"{k}={v}" for k, v in self.items())


class FactorSpace(FrozenModel):
    """The declared envelope: factors, their families and grounding, and infeasible combinations."""

    name: str = Field(description="Envelope name, e.g. the domain or customer it describes")
    version: str = Field(default="0", description="Bumped whenever a factor or level changes")
    factors: tuple[Factor, ...] = Field(description="Declared factors in declared order")
    exclusions: tuple[Cell, ...] = Field(
        default=(),
        description=(
            "Partial assignments that cannot be realised together. Combinations completing an "
            "exclusion leave the coverage denominator as 'excluded by declaration'."
        ),
    )

    @model_validator(mode="after")
    def _well_formed(self) -> "FactorSpace":
        names = [f.name for f in self.factors]
        if len(set(names)) != len(names):
            raise ValueError("factor names must be unique")
        by_name = {f.name: f for f in self.factors}
        for exclusion in self.exclusions:
            if exclusion.order < 2:
                raise ValueError(
                    f"exclusion {exclusion.label()!r} has order < 2; remove the level instead"
                )
            for factor, level in exclusion.items():
                if factor not in by_name:
                    raise ValueError(f"exclusion references unknown factor {factor!r}")
                if level not in by_name[factor].levels:
                    raise ValueError(f"exclusion references unknown level {factor}={level}")
        return self

    # -- lookups -------------------------------------------------------------------------

    @cached_property
    def _by_name(self) -> dict[str, Factor]:
        return {f.name: f for f in self.factors}

    def factor(self, name: str) -> Factor:
        """Return the factor called ``name`` or raise ``KeyError``."""
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown factor {name!r}; declared: {list(self.names)}") from exc

    def levels_of(self, name: str) -> tuple[str, ...]:
        """Levels of the named factor."""
        return self.factor(name).levels

    @property
    def names(self) -> tuple[str, ...]:
        """All factor names in declared order."""
        return tuple(f.name for f in self.factors)

    @property
    def varied(self) -> tuple[Factor, ...]:
        """Factors that are swept."""
        return tuple(f for f in self.factors if f.varied)

    @property
    def families(self) -> tuple[str, ...]:
        """Distinct family names in first-seen order."""
        seen: dict[str, None] = {}
        for f in self.factors:
            seen.setdefault(f.family, None)
        return tuple(seen)

    @property
    def pinned_cell(self) -> Cell:
        """The constant part of every full configuration."""
        return Cell(levels={f.name: f.pinned for f in self.factors if f.pinned is not None})

    @property
    def size(self) -> int:
        """Full configurations before exclusions: the product of varied level counts."""
        return prod(len(f.levels) for f in self.varied)

    def contains(self, cell: Cell) -> bool:
        """Whether every assignment in ``cell`` names a declared factor and level."""
        return all(k in self._by_name and v in self._by_name[k].levels for k, v in cell.items())

    # -- feasibility -----------------------------------------------------------------------

    @cached_property
    def forbidden(self) -> "Forbidden":
        """The exclusions as a realisability oracle (see :mod:`adversary.core.constraints`)."""
        from adversary.core.constraints import Forbidden

        return Forbidden(self.factors, self.exclusions, self.pinned_cell.levels)

    def with_pinned(self, levels: Mapping[str, str]) -> dict[str, str] | None:
        """Merge the pinned levels in; ``None`` if ``levels`` contradicts a pinned factor."""
        return self.forbidden.with_pinned(levels)

    def completes_exclusion(self, assigned: Mapping[str, str], atom: Atom) -> bool:
        """Whether adding ``atom`` to ``assigned`` completes some declared exclusion."""
        return self.forbidden.completes(assigned, atom)

    def feasible_levels(self, levels: Mapping[str, str]) -> bool:
        """Feasibility of a raw assignment, pinned levels included."""
        return self.forbidden.feasible(levels)

    def realisable_levels(self, levels: Mapping[str, str]) -> bool:
        """Exact realisability of a raw assignment under the declared exclusions."""
        return self.forbidden.realisable(levels)

    def is_feasible(self, cell: Cell) -> bool:
        """Whether ``cell``, together with the pinned levels, completes no declared exclusion.

        A cell assigning a pinned factor to a level other than its pinned level is infeasible
        in this envelope.
        """
        return self.forbidden.feasible(cell.levels)

    def is_realisable(self, cell: Cell) -> bool:
        """Whether some full configuration of this envelope contains ``cell``.

        A partial assignment can violate no exclusion directly and still be unrealisable, when
        its levels rule out, directly or through a chain of other factors, every level of some
        factor. This is decided exactly by a search over the factors the exclusions mention
        (:class:`~adversary.core.constraints.Forbidden`), so implied infeasibility is a finding
        the classification can name rather than something a construction discovers later.
        """
        return self.forbidden.realisable(cell.levels)

    def complete(self, cell: Cell) -> Cell:
        """Add the pinned levels to a cell so it is a full, runnable configuration."""
        return cell.merge(self.pinned_cell)

    def is_full(self, cell: Cell) -> bool:
        """Whether the cell assigns every varied factor."""
        return all(f.name in cell for f in self.varied)

    def _groups(self, t: int) -> Iterator[tuple[Factor, ...]]:
        varied = self.varied
        if not 1 <= t <= len(varied):
            raise ValueError(f"t must be in [1, {len(varied)}], got {t}")
        return combinations(varied, t)

    def total_combinations(self, t: int) -> int:
        """Every t-way level combination over the varied factors, before any exclusion."""
        return sum(prod(len(f.levels) for f in group) for group in self._groups(t))

    def _classified(self, t: int) -> Iterator[tuple[dict[str, str], str]]:
        """Every t-way combination with its class: 'excluded', 'implied' or 'realisable'."""
        for group in self._groups(t):
            names = [f.name for f in group]
            for levels in product(*(f.levels for f in group)):
                assignment = dict(zip(names, levels, strict=True))
                if not self.feasible_levels(assignment):
                    yield assignment, "excluded"
                elif not self.realisable_levels(assignment):
                    yield assignment, "implied"
                else:
                    yield assignment, "realisable"

    def classify(self, t: int) -> "Classification":
        """One pass over every t-way combination, sorted into the three disjoint classes."""
        realisable: list[Cell] = []
        implied: list[Cell] = []
        excluded = 0
        for assignment, kind in self._classified(t):
            if kind == "realisable":
                realisable.append(Cell(levels=assignment))
            elif kind == "implied":
                implied.append(Cell(levels=assignment))
            else:
                excluded += 1
        return Classification(
            strength=t,
            total=excluded + len(implied) + len(realisable),
            excluded_by_declaration=excluded,
            implied_infeasible=tuple(implied),
            realisable=tuple(realisable),
        )

    def combinations(self, t: int) -> Iterator[Cell]:
        """All realisable t-way partial assignments over the varied factors.

        Args:
            t: Interaction strength; ``1`` yields single levels, ``2`` yields pairs, and so on.

        Yields:
            Cells of order ``t`` that some full configuration can realise.
        """
        for assignment, kind in self._classified(t):
            if kind == "realisable":
                yield Cell(levels=assignment)

    def excluded_by_declaration(self, t: int) -> int:
        """How many t-way combinations complete a declared exclusion."""
        return sum(1 for _, kind in self._classified(t) if kind == "excluded")

    def implied_infeasible(self, t: int) -> Iterator[Cell]:
        """t-way combinations that violate no exclusion but that no configuration can realise.

        These expose factor dependencies nobody declared. They are a finding for the
        factor-space audit, not bookkeeping to subtract silently.
        """
        for assignment, kind in self._classified(t):
            if kind == "implied":
                yield Cell(levels=assignment)

    # -- grounding ---------------------------------------------------------------------------

    def grounding_of(self, cell: Cell) -> dict[str, Grounding]:
        """Grounding class of every factor the cell assigns.

        A factor the envelope does not declare is ungrounded here by definition: the search
        may invent it, but it cannot be claimed until it is declared and grounded.
        """
        return {
            name: self._by_name[name].grounding if name in self._by_name else Grounding.UNGROUNDED
            for name in cell.factors
        }

    def claimable(self, cell: Cell) -> bool:
        """Whether a region over these factors could ever be a confirmed mode."""
        return all(g is not Grounding.UNGROUNDED for g in self.grounding_of(cell).values())

    def grade(self, cell: Cell) -> int | None:
        """Confirmation grade of a region: 1 if every factor is naturally grounded or a
        deployment condition, 2 if any factor is attestable only, ``None`` if unclaimable."""
        groundings = self.grounding_of(cell).values()
        if any(g is Grounding.UNGROUNDED for g in groundings):
            return None
        return 2 if any(g is Grounding.ATTESTABLE for g in groundings) else 1

    # -- identity and persistence ------------------------------------------------------------

    def fingerprint(self) -> str:
        """Content hash of the declaration; the coverage claim cites this."""
        return sha256_json(self.model_dump(mode="json"))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FactorSpace":
        """Load a declared envelope from a caller-supplied YAML file."""
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return cls.model_validate(raw)

    def to_yaml(self, path: str | Path) -> None:
        """Write the declaration as YAML."""
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.model_dump(mode="json"), handle, sort_keys=False)


class Classification(FrozenModel):
    """Every t-way combination of an envelope, sorted into disjoint classes."""

    strength: int
    total: int = Field(description="All t-way level combinations over the varied factors")
    excluded_by_declaration: int = Field(description="Combinations completing a declared exclusion")
    implied_infeasible: tuple[Cell, ...] = Field(
        description="Combinations no exclusion forbids but no configuration can realise"
    )
    realisable: tuple[Cell, ...] = Field(description="Combinations some configuration realises")

    @property
    def feasible(self) -> int:
        """The coverage denominator: total minus excluded minus implied-infeasible."""
        return len(self.realisable)
