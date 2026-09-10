"""The confirmation receipt and the type it unlocks.

A :class:`ConfirmedMode` cannot be constructed without a :class:`ConfirmationReceipt` that
names the probe, the corpus, the sources, the episode ids and the store digest, whose digest
verifies, and whose numbers meet the criteria. The atlas and the repair layer accept only
`ConfirmedMode`, so skipping confirmation is not a policy violation but a type error.

Every receipt carries a confirmation grade: grade 1 when every
factor in the region occurs naturally in a named corpus or is a deployment condition, grade 2
when some factor is attested in production and was injected on real items. A region with an
ungrounded factor has no grade and no receipt.
"""

from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import Field, model_validator

from adversary.confirm.criteria import ConfirmationCriteria
from adversary.core.config import FrozenModel
from adversary.core.factors import Cell, Grounding
from adversary.core.util import sha256_json, utc_now
from adversary.probe.probe import Probe


class ConfirmationReceipt(FrozenModel):
    """Evidence that a probe's region reproduced on real held-out data."""

    probe_id: str
    condition: Cell
    grounding: dict[str, Grounding] = Field(
        description="Grounding class of every factor in the condition; none may be ungrounded"
    )
    grade: Literal[1, 2] = Field(description="1 if no factor is merely attestable, else 2")
    corpus_fingerprint: str
    sources: tuple[str, ...] = Field(min_length=1)
    n_mode: int = Field(ge=1, strict=True)
    mode_success: float = Field(ge=0, le=1, allow_inf_nan=False)
    n_control: int = Field(ge=1, strict=True)
    control_success: float = Field(ge=0, le=1, allow_inf_nan=False)
    p_value: float = Field(ge=0, le=1, allow_inf_nan=False)
    confirmatory_excess_points: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Rate-scale Möbius synergy over the injected factors (A5), when measured",
    )
    episode_ids: tuple[str, ...] = Field(min_length=1)
    store_digest: str
    criteria: ConfirmationCriteria
    issued_at: datetime = Field(default_factory=utc_now)
    digest: str = Field(description="Hash of every field above; recomputed by verify()")

    def _payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"digest"})

    @classmethod
    def issue(cls, **fields: object) -> "ConfirmationReceipt":
        """Construct with the digest computed over the validated fields."""
        draft = cls(**fields, digest="pending")
        return draft.model_copy(update={"digest": sha256_json(draft._payload())})

    def verify(self) -> bool:
        """Whether the digest matches the fields."""
        return self.digest == sha256_json(self._payload())

    @property
    def gap_points(self) -> float:
        return 100.0 * (self.control_success - self.mode_success)

    @property
    def discovery_free(self) -> bool:
        """True when every factor is a deployment condition; such a mode says nothing new about
        the world and the report counts it separately."""
        return all(g is Grounding.CONDITION for g in self.grounding.values())

    def meets(self, criteria: ConfirmationCriteria | None = None) -> list[str]:
        """Criteria failures; empty means the receipt supports a mode."""
        try:
            validated = type(self).model_validate(self.model_dump(mode="python"))
            c = ConfirmationCriteria.model_validate(
                (criteria or validated.criteria).model_dump(mode="python")
            )
        except ValueError as exc:
            return [f"invalid confirmation evidence: {exc}"]
        problems = []
        # model_copy intentionally skips validation; admission still rejects poisoned evidence.
        for name in ("mode_success", "control_success", "p_value"):
            value = getattr(self, name)
            if not isfinite(value) or not 0 <= value <= 1:
                problems.append(f"{name} must be a finite probability")
        if self.confirmatory_excess_points is not None and not isfinite(
            self.confirmatory_excess_points
        ):
            problems.append("confirmatory excess must be finite")
        ungrounded = sorted(f for f, g in self.grounding.items() if g is Grounding.UNGROUNDED)
        if ungrounded:
            problems.append(f"region contains ungrounded factors: {ungrounded}")
        if set(self.grounding) != set(self.condition.factors):
            problems.append("grounding must cover exactly the condition's factors")
        expected_grade = 2 if any(g is Grounding.ATTESTABLE for g in self.grounding.values()) else 1
        if self.grade != expected_grade:
            problems.append(
                f"grade {self.grade} contradicts the grounding (expected {expected_grade})"
            )
        if self.grade > c.max_grade:
            problems.append(f"grade {self.grade} exceeds the admitted maximum {c.max_grade}")
        if self.n_mode < c.min_items:
            problems.append(f"{self.n_mode} mode items < {c.min_items}")
        if self.n_control < c.min_items:
            problems.append(f"{self.n_control} control items < {c.min_items}")
        if self.mode_success > c.max_mode_success:
            problems.append(f"mode success {self.mode_success:.2f} > {c.max_mode_success:.2f}")
        if self.control_success < c.min_control_success:
            problems.append(
                f"control success {self.control_success:.2f} < {c.min_control_success:.2f}"
            )
        if self.gap_points < c.min_gap_points:
            problems.append(f"gap {self.gap_points:.1f} points < {c.min_gap_points:.1f}")
        if any(not source.strip() or source != source.strip() for source in self.sources):
            problems.append("sources require nonblank canonical identifiers")
        if len(set(self.sources)) < c.min_sources:
            problems.append(f"{len(set(self.sources))} sources < {c.min_sources}")
        if self.p_value > c.alpha:
            problems.append(f"p={self.p_value:.4f} > alpha={c.alpha}")
        if c.min_confirmatory_excess_points is not None:
            if self.confirmatory_excess_points is None:
                problems.append("confirmatory excess (branch design) required but not measured")
            elif self.confirmatory_excess_points < c.min_confirmatory_excess_points:
                problems.append(
                    f"confirmatory excess {self.confirmatory_excess_points:.1f} points < "
                    f"{c.min_confirmatory_excess_points:.1f}"
                )
        return problems


class ConfirmedMode(FrozenModel):
    """A probe plus the receipt that makes it a mode. All the atlas and the fixer accept."""

    probe: Probe
    receipt: ConfirmationReceipt

    @model_validator(mode="after")
    def _receipt_is_valid(self) -> "ConfirmedMode":
        if self.receipt.probe_id != self.probe.id:
            raise ValueError("receipt names a different probe")
        if self.receipt.condition != self.probe.cell:
            raise ValueError("receipt condition differs from the probe")
        if not self.receipt.verify():
            raise ValueError("receipt digest does not verify")
        problems = self.receipt.meets()
        if problems:
            raise ValueError("receipt does not meet confirmation criteria: " + "; ".join(problems))
        return self

    @property
    def id(self) -> str:
        return self.probe.id

    @property
    def grade(self) -> int:
        return self.receipt.grade
