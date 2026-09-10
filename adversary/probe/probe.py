"""The Probe: the unit we deliver and the unit that must survive verification.

A probe bundles a hypothesis in words, an executable generator, a code verifier, the factor
cell it covers, its evidence, the real held-out set it was checked against, and every
hypothesis killed on the way. Probes are immutable; each stage returns a new copy via
:meth:`Probe.with_`. Status stops at ``MEASURED`` here: confirmation on real data produces a
separate :class:`~adversary.confirm.receipt.ConfirmedMode` wrapper, so "mode" is a type that
cannot exist without a receipt.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.licensing import SourceNotice
from adversary.core.model import LicenseClass
from adversary.core.util import short_id, utc_now
from adversary.domain.channel import Channel
from adversary.probe.evidence import Evidence, HeldOutRef
from adversary.probe.kill import KillRecord, MinimalPair, Prediction
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.stats.excess import ExcessEstimate


class ProbeStatus(StrEnum):
    """How far a probe has got. Confirmation is a separate type, not a status."""

    DRAFT = "draft"
    """Proposed; nothing counts yet."""

    ADMITTED = "admitted"
    """Passed the critic and the solvability floor."""

    MEASURED = "measured"
    """Survived its minimal pair on generated data. Still a hypothesis."""


class ProbeProvenance(FrozenModel):
    """Who wrote the probe and against which envelope."""

    factor_space: str = Field(description="Fingerprint of the envelope the cell refers to")
    authored_by: str | None = Field(default=None, description="Model id that wrote the programs")
    author_license: LicenseClass | None = None
    source_notice: SourceNotice | None = None
    parent_id: str | None = Field(default=None, description="Probe this one was mutated from")
    created_at: datetime = Field(default_factory=utc_now)


class Probe(FrozenModel):
    """Hypothesis, ``gen``, ``check``, cell, evidence, kills."""

    id: str
    hypothesis: str = Field(description="The failure mode in words, arguable")
    generator: ProgramSource
    verifier: ProgramSource
    cell: Cell = Field(description="The region: factor levels the hypothesis is about")
    pair: MinimalPair = Field(description="Full configurations isolating one factor of the region")
    prediction: Prediction
    perturbation: ProgramSource | None = None
    channel: Channel | None = None
    clauses: tuple[str, ...] = ()
    seed: dict[str, Any] | None = None
    excess: ExcessEstimate | None = Field(
        default=None, description="Observed minus additive, when measured"
    )
    evidence: Evidence = Field(default_factory=Evidence)
    held_out: HeldOutRef | None = None
    kills: tuple[KillRecord, ...] = ()
    status: ProbeStatus = ProbeStatus.DRAFT
    provenance: ProbeProvenance

    @model_validator(mode="after")
    def _well_formed(self) -> "Probe":
        if self.perturbation is not None:
            if self.perturbation.kind is not ProgramKind.PERTURBATION:
                raise ValueError("perturbation has the wrong program kind")
            if self.channel is None or not self.seed or not self.clauses:
                raise ValueError("perturbation requires channel, seed and clauses")
            if set(self.pair.control.levels) != set(self.clauses):
                raise ValueError("pair must assign all declared clauses")
            if any(
                v not in ("on", "off")
                for c in (self.pair.control, self.pair.treatment)
                for v in c.levels.values()
            ):
                raise ValueError("clause levels must be on or off")
        elif self.channel is not None or self.clauses or self.seed is not None:
            raise ValueError("channel, clauses and seed require a perturbation program")
        if self.generator.kind is not ProgramKind.GENERATOR:
            raise ValueError("generator program must be of kind 'generator'")
        if self.verifier.kind is not ProgramKind.VERIFIER:
            raise ValueError("verifier program must be of kind 'verifier'")
        if not self.pair.treatment.covers(self.cell):
            raise ValueError("the treatment arm must realise the probe's cell")
        if self.pair.factor not in self.cell:
            raise ValueError(
                f"the pair isolates {self.pair.factor!r}, which is not part of the region; "
                "a minimal pair must flip one factor of the cell it tests"
            )
        return self

    @property
    def shippable(self) -> bool:
        """False if a restricted-licence model wrote the programs."""
        author_ok = self.provenance.author_license is LicenseClass.PERMISSIVE or (
            self.provenance.authored_by is None and self.provenance.author_license is None
        )
        source_ok = self.seed is None or (
            self.provenance.source_notice is not None and self.provenance.source_notice.shippable
        )
        return author_ok and source_ok

    @property
    def survived(self) -> int:
        return sum(1 for k in self.kills if k.verdict == "survived")

    @property
    def killed(self) -> int:
        return sum(1 for k in self.kills if k.verdict == "killed")

    def with_(self, **update: Any) -> "Probe":
        """Return a validated copy with fields replaced."""
        return type(self).model_validate({**dict(self), **update})

    def with_kill(self, record: KillRecord) -> "Probe":
        """Append a falsification record."""
        return self.with_(kills=(*self.kills, record))

    @staticmethod
    def make_id(
        hypothesis: str,
        generator: ProgramSource,
        verifier: ProgramSource,
        perturbation: ProgramSource | None = None,
    ) -> str:
        """Content-addressed id over the hypothesis and both programs."""
        return short_id(
            "probe",
            [
                hypothesis,
                generator.digest,
                verifier.digest,
                *([perturbation.digest] if perturbation else []),
            ],
        )
