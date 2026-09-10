"""Shared-task footprint and transfer arithmetic; unknown cells stay unknown."""

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from math import comb

import numpy as np
from pydantic import Field, model_validator

from adversary.core.config import FrozenModel


def jaccard(left: Sequence[bool | None], right: Sequence[bool | None]) -> float | None:
    if len(left) != len(right):
        raise ValueError("footprints require the same task universe")
    if any(x is None or y is None for x, y in zip(left, right, strict=True)):
        return None
    union = sum(bool(x or y) for x, y in zip(left, right, strict=True))
    return sum(bool(x and y) for x, y in zip(left, right, strict=True)) / union if union else None


def adjusted_rand(left: Sequence[str], right: Sequence[str]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("two complete partitions of at least two items required")
    cells = Counter(zip(left, right, strict=True))
    a, b = Counter(left), Counter(right)
    total = comb(len(left), 2)
    agree = sum(comb(n, 2) for n in cells.values())
    row, col = sum(comb(n, 2) for n in a.values()), sum(comb(n, 2) for n in b.values())
    expected = row * col / total
    ceiling = (row + col) / 2
    return (agree - expected) / (ceiling - expected) if ceiling != expected else 1.0


def partitions(
    nodes: Sequence[str], edges: Sequence[tuple[str, str]]
) -> tuple[tuple[str, ...], ...]:
    if len(set(nodes)) != len(nodes):
        raise ValueError("duplicate partition member")
    groups = [{node} for node in nodes]
    for a, b in edges:
        if a not in nodes or b not in nodes:
            raise ValueError("edge references an unknown member")
        merged = set().union(*(g for g in groups if a in g or b in g))
        groups = [g for g in groups if a not in g and b not in g] + [merged]
    return tuple(sorted(tuple(sorted(g)) for g in groups))


class FootprintTable(FrozenModel):
    corpus_digest: str
    target_pin: str
    task_ids: tuple[str, ...]
    resources: tuple[str, ...]
    values: dict[str, tuple[bool | None, ...]]
    grades: dict[str, int]

    @model_validator(mode="after")
    def _shape(self) -> "FootprintTable":
        if (
            len(set(self.task_ids)) != len(self.task_ids)
            or len(self.resources) != len(self.task_ids)
            or any(len(v) != len(self.task_ids) for v in self.values.values())
            or set(self.grades) != set(self.values)
            or any(g not in (1, 2) for g in self.grades.values())
        ):
            raise ValueError("invalid footprint dimensions, task identities, or grades")
        return self

    def similarities(self) -> dict[tuple[str, str], float | None]:
        return {
            (a, b): jaccard(self.values[a], self.values[b]) for a, b in combinations(self.values, 2)
        }

    def resample(self, seed: int) -> "FootprintTable":
        """One cluster draw applied to every column, preserving shared-task covariance."""
        keys = sorted(set(self.resources))
        if not keys:
            raise ValueError("cannot resample an empty footprint")
        rng = np.random.default_rng(seed)
        indices = [
            i
            for k in rng.choice(keys, len(keys), replace=True)
            for i, resource in enumerate(self.resources)
            if resource == k
        ]
        return self.model_copy(
            update={
                "task_ids": tuple(f"draw-{j}:{self.task_ids[i]}" for j, i in enumerate(indices)),
                "resources": tuple(self.resources[i] for i in indices),
                "values": {
                    m: tuple(values[i] for i in indices) for m, values in self.values.items()
                },
            }
        )


class TransferMatrix(FrozenModel):
    target_pin: str
    modes: tuple[str, ...]
    values: dict[str, dict[str, float | None]]
    lower: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    evidence_digest: str

    @model_validator(mode="after")
    def _square(self) -> "TransferMatrix":
        if len(set(self.modes)) != len(self.modes) or set(self.values) != set(self.modes):
            raise ValueError("transfer matrix requires distinct matching modes")
        if any(set(row) != set(self.modes) for row in self.values.values()):
            raise ValueError("transfer matrix must be square")
        if self.lower and (
            set(self.lower) != set(self.modes)
            or any(set(row) != set(self.modes) for row in self.lower.values())
        ):
            raise ValueError("transfer bound dimensions differ")
        return self

    def mutual(self, threshold: float) -> dict[tuple[str, str], bool | None]:
        results = {}
        for a, b in combinations(self.modes, 2):
            x, y = self.lower.get(a, {}).get(b), self.lower.get(b, {}).get(a)
            results[a, b] = None if x is None or y is None else min(x, y) >= threshold
        return results


def chained_components(
    components: Sequence[Sequence[str]],
    relation: Mapping[tuple[str, str], bool | None],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(group)
        for group in components
        if any(relation.get(tuple(sorted(pair))) is not True for pair in combinations(group, 2))
    )
