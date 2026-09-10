"""Falsification records: the minimal pair, the committed prediction, and the measured outcome.

A :class:`KillRecord` cannot say "killed" or "survived" independently of its numbers: the
verdict is validated against :meth:`MeasuredOutcome.supports`. Since a
:class:`MeasuredOutcome` requires episode ids and a store digest, a kill record without
measured episodes behind it is unrepresentable. The falsifier in the search layer is the only
producer; the proposer never sees this type.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.util import utc_now
from adversary.stats.equivalence import BootstrapResult, McNemarResult
from adversary.stats.rates import Comparison


class MinimalPair(FrozenModel):
    """Two full configurations differing in exactly one factor."""

    control: Cell
    treatment: Cell

    @model_validator(mode="after")
    def _differs_in_one_factor(self) -> "MinimalPair":
        if self.control.factors != self.treatment.factors:
            raise ValueError("control and treatment must assign the same factors")
        differing = [k for k in self.control.factors if self.control[k] != self.treatment[k]]
        if len(differing) != 1:
            raise ValueError(f"a minimal pair differs in exactly one factor, got {differing}")
        return self

    @property
    def factor(self) -> str:
        """The isolated factor."""
        return next(k for k in self.control.factors if self.control[k] != self.treatment[k])


class Prediction(FrozenModel):
    """A commitment that could come back negative."""

    min_effect: float = Field(
        gt=0.0,
        le=1.0,
        description="Treatment must fail at least this much more often, in probability",
    )
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0, description="Significance required")
    statement: str = Field(description="The prediction in words, as committed before running")


class MeasuredOutcome(FrozenModel):
    """What the two arms actually did, traceable to stored episodes."""

    control_n: int = Field(ge=1)
    control_failures: int = Field(ge=0)
    treatment_n: int = Field(ge=1)
    treatment_failures: int = Field(ge=0)
    effect: float = Field(description="treatment failure rate minus control failure rate")
    ci_low: float
    ci_high: float
    p_value: float = Field(ge=0.0, le=1.0)
    test: Literal["mcnemar", "fisher"] = Field(
        default="fisher",
        description="McNemar when arms are paired by instance, Fisher exact otherwise",
    )
    episode_ids: tuple[str, ...] = Field(
        min_length=1, description="Every episode behind the numbers"
    )
    store_digest: str = Field(description="Episode store digest when the record was made")

    @property
    def paired(self) -> bool:
        return self.test == "mcnemar"

    @classmethod
    def from_paired(
        cls,
        control_failed: Sequence[bool],
        treatment_failed: Sequence[bool],
        mcnemar: McNemarResult,
        bootstrap: BootstrapResult,
        episode_ids: tuple[str, ...],
        store_digest: str,
    ) -> "MeasuredOutcome":
        """Build from arms paired by instance (same seed, one factor changed)."""
        return cls(
            control_n=len(control_failed),
            control_failures=sum(control_failed),
            treatment_n=len(treatment_failed),
            treatment_failures=sum(treatment_failed),
            effect=bootstrap.mean_difference,
            ci_low=bootstrap.ci_low,
            ci_high=bootstrap.ci_high,
            p_value=mcnemar.p_value,
            test="mcnemar",
            episode_ids=episode_ids,
            store_digest=store_digest,
        )

    @classmethod
    def from_comparison(
        cls, comparison: Comparison, episode_ids: tuple[str, ...], store_digest: str
    ) -> "MeasuredOutcome":
        """Build from an unpaired two-arm comparison."""
        return cls(
            control_n=comparison.control.n,
            control_failures=comparison.control.successes,
            treatment_n=comparison.treatment.n,
            treatment_failures=comparison.treatment.successes,
            effect=comparison.effect,
            ci_low=comparison.ci_low,
            ci_high=comparison.ci_high,
            p_value=comparison.p_value,
            test="fisher",
            episode_ids=episode_ids,
            store_digest=store_digest,
        )

    def supports(self, prediction: Prediction) -> bool:
        """Whether the measurement bears out the prediction."""
        return self.effect >= prediction.min_effect and self.p_value <= prediction.alpha


class KillRecord(FrozenModel):
    """One falsification attempt, with a verdict that must agree with its numbers."""

    id: str
    hypothesis: str
    pair: MinimalPair
    prediction: Prediction
    measured: MeasuredOutcome
    verdict: Literal["killed", "survived"]
    recorded_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _verdict_follows_measurement(self) -> "KillRecord":
        expected = "survived" if self.measured.supports(self.prediction) else "killed"
        if self.verdict != expected:
            raise ValueError(
                f"verdict {self.verdict!r} contradicts the measurement; must be {expected!r}"
            )
        return self

    @staticmethod
    def verdict_for(
        measured: MeasuredOutcome, prediction: Prediction
    ) -> Literal["killed", "survived"]:
        """The only verdict consistent with the numbers."""
        return "survived" if measured.supports(prediction) else "killed"
