"""Fresh cross-evaluation with shared-task pairing and explicit denominator refusals."""

from collections.abc import Mapping, Sequence
from math import log, sqrt

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.instance import Instance
from adversary.core.model import LanguageModel
from adversary.core.util import sha256_json
from adversary.execution.harness import Harness
from adversary.stats.footprint import TransferMatrix
from adversary.stats.recall import TaskOutcome


class TransferDesign(FrozenModel):
    modes: tuple[str, ...]
    target_pin: str = Field(pattern=r"^[0-9a-f]{64}$")
    alpha: float = Field(default=0.05, gt=0, lt=1)
    minimum_base_failure: float = Field(gt=0, lt=1)
    evaluation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def eval_set(
    items: Sequence[Instance], fix_resources: Sequence[str], fix_seeds: Sequence[int]
) -> tuple[Instance, ...]:
    if not items or len({i.id for i in items}) != len(items):
        raise ValueError("nonempty distinct evaluation instances required")
    if any(i.resource is None or i.resource in fix_resources or i.seed in fix_seeds for i in items):
        raise ValueError("evaluation must be disjoint from fix resources and seeds")
    return tuple(items)


def measure_transfer(
    design: TransferDesign,
    harness: Harness,
    base: LanguageModel,
    adapters: Mapping[str, Sequence[LanguageModel]],
    placebos: Sequence[LanguageModel],
    items: Mapping[str, Sequence[Instance]],
) -> TransferMatrix:
    """Whole square; bounds use independent resource means and retain paired covariance.

    Scores average the registered adapter seeds. Missing executions invalidate a matrix cell.
    Intervals are conservative Hoeffding bounds, not degenerate empirical bootstrap intervals.
    """
    if set(items) != set(design.modes) or set(adapters) != set(design.modes):
        raise ValueError("evaluation and adapter sets must match the registered square")
    if not placebos or any(not models for models in adapters.values()):
        raise ValueError("mode adapters and matched placebo models are required")
    payload = {m: [i.model_dump(mode="json") for i in items[m]] for m in sorted(items)}
    if sha256_json(payload) != design.evaluation_digest:
        raise ValueError("evaluation draw changed after registration")
    values = {a: {} for a in design.modes}
    lower = {a: {} for a in design.modes}
    evidence = []
    for mode in design.modes:
        batch = items[mode]
        ids = [i.id for i in batch]
        if not batch or len(set(ids)) != len(ids) or any(i.resource is None for i in batch):
            raise ValueError("distinct evaluation items with resource identities required")

        def run(
            model: LanguageModel,
            batch: Sequence[Instance] = batch,
            mode: str = mode,
            ids: list[str] = ids,
        ) -> list[float] | None:
            report = harness.run(batch, model, arm=f"transfer:{mode}")
            evidence.extend(e.model_dump(mode="json") for e in report.episodes)
            if len(report.episodes) != len(batch) or any(not e.measurable for e in report.episodes):
                return None
            rows = {e.instance_id: e for e in report.episodes}
            if set(rows) != set(ids):
                return None
            return [float(rows[i].failed) for i in ids]

        b = run(base)
        controls = [run(model) for model in placebos]
        for name in design.modes:
            treated = [run(model) for model in adapters[name]]
            all_rows = [b, *controls, *treated]
            if any(row is None for row in all_rows):
                values[name][mode] = lower[name][mode] = None
                continue
            groups = [
                [i for i, item in enumerate(batch) if item.resource == r]
                for r in sorted({item.resource for item in batch})
            ]
            denominator = sum(sum(b[i] for i in g) / len(g) for g in groups) / len(groups)
            numerator = sum(
                sum(
                    sum(row[i] for row in controls) / len(controls)
                    - sum(row[i] for row in treated) / len(treated)
                    for i in g
                )
                / len(g)
                for g in groups
            ) / len(groups)
            cell_alpha = design.alpha / (len(design.modes) ** 2)
            base_radius = sqrt(log(4 / cell_alpha) / (2 * len(groups)))
            gain_radius = 2 * base_radius
            dl, du = max(0.0, denominator - base_radius), min(1.0, denominator + base_radius)
            if dl <= design.minimum_base_failure:
                values[name][mode] = lower[name][mode] = None
            else:
                values[name][mode] = numerator / denominator
                nl = max(-1.0, numerator - gain_radius)
                lower[name][mode] = min(nl / dl, nl / du)
    return TransferMatrix(
        target_pin=design.target_pin,
        modes=design.modes,
        values=values,
        lower=lower,
        evidence_digest=sha256_json(evidence),
    )


def real_diagonal(
    base: Sequence[TaskOutcome],
    adapter: Sequence[TaskOutcome],
    placebo: Sequence[TaskOutcome],
    minimum_base_failure: float,
) -> dict:
    if [o.task_id for o in base] != [o.task_id for o in adapter] or [o.task_id for o in base] != [
        o.task_id for o in placebo
    ]:
        raise ValueError("real diagonal requires paired task groups")
    unknown = sum(
        any(o.failure is None for o in group) for group in zip(base, adapter, placebo, strict=True)
    )
    if not base or unknown:
        return {"gain": None, "unresolved": unknown, "refusal": "incomplete real-task groups"}
    denominator = sum(o.failure for o in base) / len(base)
    if denominator <= minimum_base_failure:
        return {"gain": None, "unresolved": 0, "refusal": "base failure denominator near zero"}
    gain = (
        (sum(o.failure for o in placebo) - sum(o.failure for o in adapter))
        / len(base)
        / denominator
    )
    return {"gain": gain, "unresolved": 0, "label": "descriptive; release proof required"}
