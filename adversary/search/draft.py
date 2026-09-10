"""A proposed probe before anything has been checked."""

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.model import ModelInfo
from adversary.domain.channel import Channel
from adversary.probe.kill import MinimalPair, Prediction
from adversary.probe.probe import Probe, ProbeProvenance, ProbeStatus
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.search.context import MinedSeed


class ProbeDraft(FrozenModel):
    """Hypothesis, programs, cell, pair and prediction as proposed."""

    hypothesis: str
    generator: ProgramSource
    verifier: ProgramSource
    cell: Cell
    perturbation: ProgramSource | None = None
    channel: Channel | None = None
    clauses: tuple[str, ...] = ()
    seed: MinedSeed | None = None
    pair: MinimalPair
    prediction: Prediction
    authored_by: ModelInfo | None = Field(default=None, description="The proposing model")
    parent_id: str | None = Field(default=None, description="Set when this is a mutation")

    @model_validator(mode="after")
    def _program_contract(self) -> "ProbeDraft":
        if self.generator.kind is not ProgramKind.GENERATOR:
            raise ValueError("generator has the wrong program kind")
        if self.verifier.kind is not ProgramKind.VERIFIER:
            raise ValueError("verifier has the wrong program kind")
        if self.perturbation is None:
            if self.channel is not None or self.seed is not None or self.clauses:
                raise ValueError("v2 declarations require the third program")
            return self
        if self.perturbation.kind is not ProgramKind.PERTURBATION:
            raise ValueError("perturbation has the wrong program kind")
        if self.channel is None or self.seed is None:
            raise ValueError("v2 requires channel and mined seed")
        if not self.clauses or len(set(self.clauses)) != len(self.clauses):
            raise ValueError("clauses must be nonempty and unique")
        if any(not name.strip() for name in self.clauses):
            raise ValueError("clause names must be nonempty")
        for cell in (self.pair.control, self.pair.treatment):
            if set(cell.levels) != set(self.clauses):
                raise ValueError("both pair arms must assign every declared clause")
            if any(level not in ("on", "off") for level in cell.levels.values()):
                raise ValueError("clause levels must be on or off")
        if self.cell != self.pair.treatment:
            raise ValueError("draft cell must match the declared treatment")
        return self

    def to_probe(self, factor_space_fingerprint: str) -> Probe:
        """Promote to a ``DRAFT`` probe."""
        return Probe(
            id=Probe.make_id(self.hypothesis, self.generator, self.verifier, self.perturbation),
            hypothesis=self.hypothesis,
            generator=self.generator,
            verifier=self.verifier,
            cell=self.cell,
            perturbation=self.perturbation,
            channel=self.channel,
            clauses=self.clauses,
            seed=self.seed.model_dump(mode="json") if self.seed else None,
            pair=self.pair,
            prediction=self.prediction,
            status=ProbeStatus.DRAFT,
            provenance=ProbeProvenance(
                factor_space=factor_space_fingerprint,
                authored_by=self.authored_by.id if self.authored_by else None,
                author_license=self.authored_by.license if self.authored_by else None,
                parent_id=self.parent_id,
            ),
        )
