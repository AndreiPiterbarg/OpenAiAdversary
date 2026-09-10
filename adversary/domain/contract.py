"""The plugin contract: exactly three kinds of thing a domain supplies.

1. :class:`EnvironmentBuilder` declares the factors it can realise, generates instances for
   a cell, instantiates them as live :class:`Environment` objects, and supplies the domain's
   default :class:`~adversary.core.verify.Verifier`.
2. :class:`Reference` certifies solvability: a clean reference run (or construction proof) and,
   when perturbations are present, an executed recovery witness with them present. This is the
   solvability floor borrowed from PAIRED, made perturbation-present by Amendment A3;
   impossibility
   earns the adversary nothing.
3. :class:`RealCorpus` supplies real held-out items for a condition. Nothing is a mode until
   it reproduces here.

:class:`Domain` binds the three. It uses ``__slots__`` so a fourth attribute cannot be added
at runtime: if a plugin needs one, the core has leaked and the fix is in the core.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell, FactorSpace
from adversary.core.generator import Generator
from adversary.core.instance import Instance
from adversary.core.model import LanguageModel
from adversary.core.trajectory import Budget, Trajectory
from adversary.core.verify import Verifier


class Environment(ABC):
    """A live task the target acts in. Owns the loop that runs a model against itself."""

    @abstractmethod
    def run(self, model: LanguageModel, budget: Budget) -> Trajectory:
        """Run ``model`` in this environment until it stops or the budget is exhausted.

        The returned trajectory must carry ``final_state`` sufficient for offline
        verification and ``claimed_success`` if the environment elicits a self-report.
        """

    def close(self) -> None:  # noqa: B027 - a no-op default is the intended contract
        """Release resources. Called by the harness after verification."""

    def __enter__(self) -> "Environment":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class EnvironmentBuilder(ABC):
    """Realises factor cells as instances and instances as environments."""

    @property
    @abstractmethod
    def factor_space(self) -> FactorSpace:
        """Every factor and level this builder can realise."""

    @abstractmethod
    def generator(self, cell: Cell, seed: int) -> Generator:
        """A seed-deterministic generator of instances realising the full configuration ``cell``."""

    @abstractmethod
    def build(self, instance: Instance) -> Environment:
        """Instantiate ``instance.spec`` as a live environment. Raise on failure; the harness
        records a :class:`~adversary.core.episode.BuildFailure` and counts the cell as not
        reached."""

    @abstractmethod
    def verifier(self) -> Verifier:
        """The domain's default oracle for instances this builder generates."""

    def pin_bindings(self, model: LanguageModel, budget: Budget) -> dict[str, Any]:
        """Observed execution bindings, excluding model identity and checkpoint.

        Implementations derive these from the actual runtime configuration; copying a
        requested pin is not verification. Missing bindings cannot validate pinned claims.
        """
        return {}


class SolvabilityCertificate(FrozenModel):
    """Evidence that an instance is hard rather than impossible.

    The floor has two halves. The *clean* half says the task is solvable with every
    perturbation removed. The *perturbed* half records fresh recovery runs with the intervention
    disclosed and the ordinary tools and budget. Failure to find a witness does not establish
    impossibility. A successful witness may seed repair, so its stored trajectory id is recorded;
    subsequent evaluations still start fresh.
    """

    instance_id: str
    method: Literal["reference_run", "construction"] = Field(
        description="How the clean half was established"
    )
    clean_passed: bool = Field(strict=True, description="Solvable with every perturbation removed")
    perturbations: tuple[str, ...] = Field(
        default=(), description="Labels of the perturbations present in the instance"
    )
    perturbed_runs: int = Field(
        default=0, ge=0, strict=True, description="Perturbed reference runs attempted"
    )
    perturbed_passed: int = Field(default=0, ge=0, strict=True, description="Of which passed")
    required_runs: int = Field(
        default=3, ge=1, strict=True, description="Perturbed runs that must all pass"
    )
    witness_id: str | None = Field(
        default=None, description="Stored perturbed reference trajectory, if one was kept"
    )
    evidence: str = Field(description="What was run or which construction guarantees it")
    reference_model: str | None = Field(default=None, description="Model id if a reference ran")

    @model_validator(mode="after")
    def coherent_counts(self) -> "SolvabilityCertificate":
        if self.perturbed_passed > self.perturbed_runs:
            raise ValueError("passed witnesses exceed attempted witnesses")
        if len(set(self.perturbations)) != len(self.perturbations) or any(
            not label.strip() for label in self.perturbations
        ):
            raise ValueError("perturbation labels must be unique and nonempty")
        return self

    @property
    def solvable(self) -> bool:
        """Clean half passed and, when perturbed, every required perturbed run passed."""
        try:
            type(self).model_validate(self.model_dump(warnings=False))
        except (ValueError, TypeError):
            return False
        if not self.clean_passed:
            return False
        if not self.perturbations:
            return True
        return (
            self.perturbed_runs >= self.required_runs
            and self.perturbed_passed == self.perturbed_runs
        )

    @property
    def witness_failed(self) -> bool:
        """A missing or unsuccessful witness is not a proof of impossibility."""
        return self.clean_passed and bool(self.perturbations) and not self.solvable

    @property
    def unrecoverable(self) -> bool:
        """Solvable clean, not solvable with the perturbations present."""
        return False  # A failed bounded search is not an impossibility proof.


class Reference(ABC):
    """The solvability floor. An unsuccessful reference leaves solvability unestablished."""

    @abstractmethod
    def certify(self, instance: Instance) -> SolvabilityCertificate:
        """Establish whether ``instance`` is solvable with its perturbations removed."""


class CorpusSource(FrozenModel):
    """One real data source inside a corpus, with the caveats a lab will ask about."""

    name: str
    provenance: str = Field(description="Where it came from and at which pin")
    license: str
    contamination_notes: str = Field(
        default="", description="Overlap with public benchmarks or the target's training cutoff"
    )


class RealCorpus(ABC):
    """Real held-out items, too few to train on, enough to test on."""

    @property
    @abstractmethod
    def sources(self) -> tuple[CorpusSource, ...]:
        """Independent sources; confirmation requires at least two."""

    @abstractmethod
    def sample(
        self, condition: Cell, n: int, seed: int, source: str | None = None
    ) -> list[Instance]:
        """Draw up to ``n`` real items matching ``condition``.

        Args:
            condition: Partial cell describing the region; the corpus decides how factors map
                onto real items and must document unmappable factors.
            n: Requested count. Fewer may be returned; the confirmer checks the minimum.
            seed: Deterministic sampling seed.
            source: Restrict to one named source, or ``None`` for all.
        """

    @abstractmethod
    def fingerprint(self) -> str:
        """Content hash of the corpus manifest so a confirmation receipt names what it ran on."""


@dataclass(frozen=True, slots=True)
class Domain:
    """A registered domain plugin: a name and exactly three components."""

    name: str
    environment: EnvironmentBuilder
    reference: Reference
    corpus: RealCorpus
