"""Task-level outcomes and recall; repeated executions are not independent tasks."""

from collections.abc import Sequence

import numpy as np
from pydantic import Field
from scipy.stats import beta

from adversary.core.config import FrozenModel


class TaskOutcome(FrozenModel):
    task_id: str
    resource: str
    passed: tuple[bool | None, ...] = Field(min_length=5, max_length=5)

    @property
    def failure(self) -> bool | None:
        return sum(x is True for x in self.passed) <= 1 if None not in self.passed else None

    @property
    def severity(self) -> float | None:
        return 1 - sum(x is True for x in self.passed) / 5 if None not in self.passed else None


def clopper_pearson(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if not 0 <= successes <= n or not 0 < alpha < 1:
        raise ValueError("invalid binomial counts or confidence level")
    if not n:
        return 0.0, 1.0
    low = float(beta.ppf(alpha / 2, successes, n - successes + 1)) if successes else 0.0
    high = float(beta.ppf(1 - alpha / 2, successes + 1, n - successes)) if successes < n else 1.0
    return low, high


class OutcomeRecall(FrozenModel):
    attempted_tasks: int
    unresolved_tasks: int
    failures: int
    zero_pass_tasks: int
    captured: int
    recall: float | None
    interval: tuple[float, float] | None
    severity_recall: float | None
    severity_interval: tuple[float, float] | None
    interval_method: str
    refusal: str | None = None


def outcome_recall(
    outcomes: Sequence[TaskOutcome],
    flags: Sequence[bool],
    *,
    iid_tasks: bool = False,
    alpha: float = 0.05,
    resamples: int = 1000,
    seed: int = 0,
) -> OutcomeRecall:
    """CP only for an explicitly registered iid task draw; otherwise refuse exactness.

    Weighted recall uses a shared-resource bootstrap over complete task groups. It remains
    conditional on complete observations; unresolved groups and the refusal stay visible.
    """
    if len(outcomes) != len(flags) or len({o.task_id for o in outcomes}) != len(outcomes):
        raise ValueError("distinct tasks and one frozen prediction per task required")
    complete = [(o, flag) for o, flag in zip(outcomes, flags, strict=True) if o.failure is not None]
    failed = [(o, flag) for o, flag in complete if o.failure]
    captured = sum(flag for _, flag in failed)
    weights = np.array([o.severity for o, _ in complete], dtype=float)
    predicted = np.array([flag for _, flag in complete], dtype=float)
    weighted = float(weights @ predicted / weights.sum()) if weights.sum() else None
    interval = clopper_pearson(captured, len(failed), alpha) if failed and iid_tasks else None
    if iid_tasks and len({o.resource for o in outcomes}) != len(outcomes):
        raise ValueError("repeated resources do not support the registered iid-task interval")
    draws = []
    resources = sorted({o.resource for o, _ in complete})
    if weighted is not None and len(resources) > 1 and resamples > 0:
        groups = [
            np.array([i for i, (o, _) in enumerate(complete) if o.resource == key])
            for key in resources
        ]
        rng = np.random.default_rng(seed)
        for _ in range(resamples):
            ids = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
            if weights[ids].sum():
                draws.append(float(weights[ids] @ predicted[ids] / weights[ids].sum()))
    severity_interval = (
        tuple(float(v) for v in np.quantile(draws, [alpha / 2, 1 - alpha / 2])) if draws else None
    )
    reasons = []
    if not failed:
        reasons.append("no complete failing-task denominator")
    if len(complete) != len(outcomes):
        reasons.append("unresolved task groups; results condition on completion")
    if not iid_tasks:
        reasons.append("exact recall interval requires the registered sampling design")
    return OutcomeRecall(
        attempted_tasks=len(outcomes),
        unresolved_tasks=len(outcomes) - len(complete),
        failures=len(failed),
        zero_pass_tasks=sum(not any(o.passed) for o, _ in complete),
        captured=captured,
        recall=captured / len(failed) if failed else None,
        interval=interval,
        severity_recall=weighted,
        severity_interval=severity_interval,
        interval_method="Clopper-Pearson" if iid_tasks else "withheld",
        refusal="; ".join(reasons) or None,
    )
