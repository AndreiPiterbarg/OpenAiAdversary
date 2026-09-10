"""Seal predicates before drawing outcomes; aggregate the registered five executions."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode
from adversary.core.factors import Cell
from adversary.core.instance import Instance
from adversary.core.util import sha256_json
from adversary.stats.recall import OutcomeRecall, TaskOutcome, outcome_recall


class FrozenPredicates(FrozenModel):
    target_pin: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicates: dict[str, Cell]
    main_n: int = Field(ge=1)
    pilot_ids: tuple[str, ...] = ()

    def seal(self, path: Path) -> str:
        """Exclusive creation prevents silently replacing a pre-draw registration."""
        with path.open("x") as handle:
            handle.write(self.model_dump_json())
        return sha256_json(self.model_dump(mode="json"))

    def assert_sealed(self, path: Path, expected_digest: str) -> None:
        stored = FrozenPredicates.model_validate_json(path.read_text())
        if stored != self or sha256_json(stored.model_dump(mode="json")) != expected_digest:
            raise ValueError("predicates or draw registration changed after sealing")


def task_outcomes(
    planned: Mapping[str, Sequence[str]],
    episodes: Sequence[Episode],
    resources: Mapping[str, str],
) -> tuple[TaskOutcome, ...]:
    """Missing and unrealised executions remain unknown; reject duplicate observations."""
    expected = [i for group in planned.values() for i in group]
    if any(len(group) != 5 for group in planned.values()) or len(set(expected)) != len(expected):
        raise ValueError("each task requires five distinct planned instance IDs")
    if len({e.instance_id for e in episodes}) != len(episodes):
        raise ValueError("duplicate execution in task aggregation")
    if any(e.instance_id not in expected for e in episodes):
        raise ValueError("unplanned execution")
    by_id = {e.instance_id: e for e in episodes}
    return tuple(
        TaskOutcome(
            task_id=task,
            resource=resources[task],
            passed=tuple(
                by_id[i].verdict.passed if i in by_id and by_id[i].measurable else None for i in ids
            ),
        )
        for task, ids in planned.items()
    )


def measure_recall(
    frozen: FrozenPredicates,
    seal_path: Path,
    seal_digest: str,
    items: Sequence[Instance],
    outcomes: Sequence[TaskOutcome],
    *,
    iid_tasks: bool = False,
) -> OutcomeRecall:
    frozen.assert_sealed(seal_path, seal_digest)
    ids = [i.id for i in items]
    if len(items) != frozen.main_n or set(ids) & set(frozen.pilot_ids):
        raise ValueError("draw size changed or pilot reused in main draw")
    if ids != [o.task_id for o in outcomes]:
        raise ValueError("task outcomes do not match the sealed draw")
    flags = [any(i.cell.covers(c) for c in frozen.predicates.values()) for i in items]
    return outcome_recall(outcomes, flags, iid_tasks=iid_tasks)


def measure_repaired(before: Sequence[TaskOutcome], after: Sequence[TaskOutcome]) -> dict:
    if [o.task_id for o in before] != [o.task_id for o in after]:
        raise ValueError("repair comparison requires the same planned tasks")
    eligible = [(b, a) for b, a in zip(before, after, strict=True) if b.failure is True]
    repaired = sum(a.failure is False for _, a in eligible)
    unknown = sum(a.failure is None for _, a in eligible)
    return {
        "base_failures": len(eligible),
        "repaired": repaired,
        "unresolved": unknown,
        "fraction": repaired / len(eligible) if eligible and not unknown else None,
    }
