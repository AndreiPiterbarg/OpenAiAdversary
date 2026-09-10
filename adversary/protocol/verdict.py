"""Computing the verdict against pre-declared kill rules. Code decides; the author reads.

Three outcomes, not two. A rule *triggers* when its preconditions and all its conditions hold.
A rule is *inconclusive* when a precondition fails or its metric is missing (the instrument has
not shown it could detect the effect, so its null is not evidence), or when it does not trigger
but its survival conditions fail (the result sits between the kill and pass thresholds). A rule
is *undeterminable* when a promised kill metric is missing although the preconditions held: the
analysis plan was not followed, and silence cannot pass, so that counts as killed.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.manifest import MANIFEST_NAME, Manifest
from adversary.core.util import utc_now
from adversary.protocol.preregistration import (
    PREREGISTRATION_FILE,
    RESULTS_DIR,
    VERDICT_FILE,
    Condition,
    KillRule,
    Preregistration,
    PreregistrationError,
    load_registration,
    verify,
)

RuleStatus = Literal["triggered", "not_triggered", "inconclusive", "undeterminable"]
Outcome = Literal["killed", "survived", "inconclusive"]


class ConditionResult(FrozenModel):
    """One condition against its measured value."""

    condition: Condition
    measured: float | None = Field(description="None if the metric was not reported")
    threshold: float | None = Field(
        description="The bound used; None if a threshold metric was missing"
    )
    holds: bool | None = Field(description="None if it could not be evaluated")


class RuleResult(FrozenModel):
    """One kill rule evaluated."""

    rule: KillRule
    preconditions: tuple[ConditionResult, ...]
    conditions: tuple[ConditionResult, ...]
    survival: tuple[ConditionResult, ...] = ()
    status: RuleStatus

    @property
    def triggered(self) -> bool:
        return self.status == "triggered"


class ExperimentVerdict(FrozenModel):
    """The outcome of an experiment against its own pre-declared rules."""

    registration_sha256: str
    results_digest: str
    rules: tuple[RuleResult, ...]
    outcome: Outcome = Field(
        description=(
            "'killed' if any rule triggered or was undeterminable; 'inconclusive' if none did "
            "but some rule's preconditions failed; 'survived' otherwise"
        )
    )
    computed_at: datetime = Field(default_factory=utc_now)

    @property
    def killed(self) -> bool:
        return self.outcome == "killed"

    @property
    def triggered(self) -> tuple[str, ...]:
        return tuple(r.rule.name for r in self.rules if r.triggered)


def _evaluate_conditions(
    conditions: tuple[Condition, ...], metrics: dict[str, float]
) -> tuple[ConditionResult, ...]:
    out = []
    for condition in conditions:
        measured = metrics.get(condition.metric)
        threshold = (
            metrics.get(condition.threshold_metric)
            if condition.threshold_metric
            else condition.threshold
        )
        holds = (
            None if measured is None or threshold is None else condition.holds(measured, threshold)
        )
        out.append(
            ConditionResult(
                condition=condition, measured=measured, threshold=threshold, holds=holds
            )
        )
    return tuple(out)


def evaluate(preregistration: Preregistration, metrics: dict[str, float]) -> list[RuleResult]:
    """Apply every rule under the three-outcome semantics."""
    results = []
    for rule in preregistration.kill_rules:
        preconditions = _evaluate_conditions(rule.requires, metrics)
        conditions = _evaluate_conditions(rule.all_of, metrics)
        survival = _evaluate_conditions(rule.survive_if, metrics)
        if any(c.holds is not True for c in preconditions):
            status: RuleStatus = "inconclusive"
        elif any(c.holds is None for c in conditions):
            status = "undeterminable"
        elif all(c.holds for c in conditions):
            status = "triggered"
        elif any(c.holds is not True for c in survival):
            status = "inconclusive"
        else:
            status = "not_triggered"
        results.append(
            RuleResult(
                rule=rule,
                preconditions=preconditions,
                conditions=conditions,
                survival=survival,
                status=status,
            )
        )
    return results


def outcome_of(rules: list[RuleResult]) -> Outcome:
    """Fold rule statuses into the experiment outcome."""
    if any(r.status in ("triggered", "undeterminable") for r in rules):
        return "killed"
    if any(r.status == "inconclusive" for r in rules):
        return "inconclusive"
    return "survived"


def decide(directory: str | Path, metrics_file: str = "metrics.json") -> ExperimentVerdict:
    """Compute and write ``verdict.json`` from sealed results.

    Refuses unless the whole chain verifies: a verdict over a broken chain would be a verdict
    over results that could have been backfilled.
    """
    root = Path(directory)
    registration = load_registration(root)
    results = root / RESULTS_DIR
    if not (results / MANIFEST_NAME).exists():
        raise PreregistrationError("results are not sealed; seal them before deciding")
    problems = verify(root)
    if problems:
        raise PreregistrationError("the hash chain is broken: " + "; ".join(problems))
    manifest = Manifest.read(results)
    metrics_path = results / metrics_file
    if not metrics_path.exists():
        raise PreregistrationError(f"{metrics_path} does not exist")
    if metrics_file not in {f.path for f in manifest.files}:
        raise PreregistrationError(
            f"{metrics_file} is not in the sealed manifest; seal results first"
        )
    raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics = {
        k: float(v)
        for k, v in raw.items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }
    preregistration = Preregistration.from_yaml(root / PREREGISTRATION_FILE)
    rules = evaluate(preregistration, metrics)
    verdict = ExperimentVerdict(
        registration_sha256=registration.sha256,
        results_digest=manifest.digest(),
        rules=tuple(rules),
        outcome=outcome_of(rules),
    )
    (root / VERDICT_FILE).write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
    return verdict
