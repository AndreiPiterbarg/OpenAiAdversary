"""Natural and injected footprints on one frozen task draw."""

from collections.abc import Mapping, Sequence

from adversary.core.factors import Cell
from adversary.core.instance import Instance
from adversary.stats.footprint import FootprintTable
from adversary.stats.recall import TaskOutcome


def footprints_from_episodes(
    items: Sequence[Instance],
    outcomes: Sequence[TaskOutcome],
    conditions: Mapping[str, Cell],
    *,
    corpus_digest: str,
    target_pin: str,
) -> FootprintTable:
    """Grade-one membership uses the observed cell in the correct covers direction."""
    if [i.id for i in items] != [o.task_id for o in outcomes]:
        raise ValueError("footprint items and task outcomes differ")
    values = {}
    for name, condition in conditions.items():
        values[name] = tuple(
            None
            if o.failure is None or not set(condition.factors) <= set(i.cell.factors)
            else bool(o.failure and i.cell.covers(condition))
            for i, o in zip(items, outcomes, strict=True)
        )
    return FootprintTable(
        corpus_digest=corpus_digest,
        target_pin=target_pin,
        task_ids=tuple(i.id for i in items),
        resources=tuple(o.resource for o in outcomes),
        values=values,
        grades={name: 1 for name in conditions},
    )


def measure_injected_footprints(
    clean: Sequence[TaskOutcome],
    injected: Mapping[str, Sequence[TaskOutcome]],
    *,
    corpus_digest: str,
    target_pin: str,
) -> FootprintTable:
    ids = tuple(o.task_id for o in clean)
    if any(tuple(o.task_id for o in rows) != ids for rows in injected.values()):
        raise ValueError("every injected mode requires the same frozen task draw")
    values = {
        name: tuple(
            None if b.failure is None or a.failure is None else bool(not b.failure and a.failure)
            for b, a in zip(clean, rows, strict=True)
        )
        for name, rows in injected.items()
    }
    return FootprintTable(
        corpus_digest=corpus_digest,
        target_pin=target_pin,
        task_ids=ids,
        resources=tuple(o.resource for o in clean),
        values=values,
        grades={name: 2 for name in injected},
    )
