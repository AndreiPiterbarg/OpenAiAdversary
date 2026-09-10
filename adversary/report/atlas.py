"""The atlas: what ships.

Declared factor space, the sweep with every cell's result, the coverage claims, the ranked
modes with their grades, the kill log, the explicit not-reached statement, the transfer table
and the non-regression proof. Modes are :class:`ConfirmedMode` by type. Every probe must be
shippable.
"""

from datetime import datetime

from pydantic import Field, model_validator

from adversary.confirm.receipt import ConfirmedMode
from adversary.core.config import FrozenModel
from adversary.core.factors import FactorSpace
from adversary.core.model import ModelInfo
from adversary.core.util import utc_now
from adversary.probe.kill import KillRecord
from adversary.protocol.planted import RelativeRecall
from adversary.repair.proof import ProofResult
from adversary.report.not_reached import NotReached
from adversary.stats.excess import ExcessEstimate
from adversary.stats.importance import Importance
from adversary.stats.interaction_order import InteractionOrderCurve
from adversary.stats.multiplicity import PermutationNull
from adversary.stats.species import SpeciesEstimate, ValidityCheck


class RankedMode(FrozenModel):
    """A confirmed mode with its importance."""

    mode_id: str
    importance: Importance


class Atlas(FrozenModel):
    """The deliverable document, as data."""

    title: str
    target: ModelInfo
    factor_space: FactorSpace
    interaction_order: InteractionOrderCurve | None = None
    hot_cells: tuple[ExcessEstimate, ...] = Field(
        description="Cells ranked by excess over the no-interaction prediction"
    )
    modes: tuple[ConfirmedMode, ...]
    ranking: tuple[RankedMode, ...] = Field(description="Modes by importance, highest first")
    kills: tuple[KillRecord, ...] = Field(
        description="Every falsification attempt, survived or killed"
    )
    not_reached: NotReached
    proof: ProofResult | None = None
    plant_recall: RelativeRecall | None = Field(
        default=None, description="Relative recall of planted modes by order (A8)"
    )
    detection_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Measured detection rate d; per-cell zero-failure bounds are 3/(n d)",
    )
    permutation_null: PermutationNull | None = Field(
        default=None, description="Empirical false-discovery rate of the region test (A8)"
    )
    undeclared_space: SpeciesEstimate | None = Field(
        default=None,
        description="Unseen-species estimate; printable only from a validated sentinel arm (A9)",
    )
    undeclared_space_validity: ValidityCheck | None = None
    registration_sha256: str | None = Field(
        default=None, description="Pre-registration this atlas answers to"
    )
    generated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _shippable(self) -> "Atlas":
        unshippable = [m.id for m in self.modes if not m.probe.shippable]
        if unshippable:
            raise ValueError(
                f"modes authored under a restricted licence cannot ship: {unshippable}"
            )
        ranked = {r.mode_id for r in self.ranking}
        known = {m.id for m in self.modes}
        if not ranked <= known:
            raise ValueError(f"ranking names unknown modes: {sorted(ranked - known)}")
        if self.undeclared_space is not None:
            if self.undeclared_space.source != "sentinel":
                raise ValueError("an undeclared-space estimate may only come from the sentinel arm")
            if self.undeclared_space_validity is None or not self.undeclared_space_validity.valid:
                raise ValueError(
                    "an undeclared-space estimate needs a passed validity check; omit it otherwise"
                )
        return self

    @property
    def coverage_language(self) -> str:
        """What the t=3 coverage claim may say, given plant recall (Amendment A8)."""
        if self.plant_recall is None:
            return "visited only; plant recall not measured"
        r3 = self.plant_recall.by_order.get(3, float("nan"))
        r2 = self.plant_recall.by_order.get(2, float("nan"))
        if r2 >= 0.8 and r3 >= 0.8:
            return f"complete at t=3 with relative recall {r3:.2f} attached"
        if r3 >= 0.5:
            return f"visited, recall {r3:.2f}"
        return "t=3 completeness withdrawn: three-way relative recall below 0.5"

    @property
    def killed(self) -> int:
        return sum(1 for k in self.kills if k.verdict == "killed")

    @property
    def survived(self) -> int:
        return sum(1 for k in self.kills if k.verdict == "survived")

    @property
    def grade_counts(self) -> dict[int, int]:
        """Confirmed modes per grade; a lab will ask how many were found in the wild."""
        return {g: sum(1 for m in self.modes if m.grade == g) for g in (1, 2)}

    @property
    def discovery_free_modes(self) -> int:
        """Modes whose every factor is a deployment condition."""
        return sum(1 for m in self.modes if m.receipt.discovery_free)
