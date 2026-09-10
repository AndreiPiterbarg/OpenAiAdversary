"""Explicitly indexed, frozen real tasks. Unknown properties are never filled in."""

import json
import random
from pathlib import Path

from adversary.core.factors import Cell
from adversary.core.instance import Instance
from adversary.core.util import sha256_bytes, sha256_json
from adversary.domain.contract import CorpusSource, RealCorpus


class CorpusNotBuilt(RuntimeError):
    """No explicit corpus index was supplied."""


class SweRealCorpus(RealCorpus):
    """Sample without replacement using observed cells only.

    A source is a collection, not proof of an independent collection organisation.
    Discovery/confirmation disjointness is checked when the pools are registered.
    """

    def __init__(
        self,
        *,
        sources: tuple[CorpusSource, ...] = (),
        items: dict[str, tuple[Instance, ...]] | None = None,
    ) -> None:
        if not sources or items is None:
            raise CorpusNotBuilt("supply explicit sources and a frozen item index")
        if len({s.name for s in sources}) != len(sources) or set(items) != {
            s.name for s in sources
        }:
            raise ValueError("source metadata and index must match exactly")
        rows = [i for group in items.values() for i in group]
        if len({i.id for i in rows}) != len(rows):
            raise ValueError("duplicate task IDs across corpus sources")
        self._sources = sources
        # Own JSON bytes: caller mutations cannot change the frozen draw.
        self._items = {s: tuple(i.model_dump_json() for i in group) for s, group in items.items()}
        self._fingerprint = sha256_json(
            {"sources": [s.model_dump() for s in sources], "items": self._items}
        )

    @classmethod
    def from_manifest(cls, path: Path, expected_sha256: str) -> "SweRealCorpus":
        data = path.read_bytes()
        if sha256_bytes(data) != expected_sha256:
            raise ValueError("corpus manifest differs from the frozen registration")
        raw = json.loads(data)
        if set(raw) != {"sources", "items"}:
            raise ValueError("corpus manifest requires sources and items")
        return cls(
            sources=tuple(CorpusSource.model_validate(s) for s in raw["sources"]),
            items={
                name: tuple(Instance.model_validate(i) for i in group)
                for name, group in raw["items"].items()
            },
        )

    @property
    def sources(self) -> tuple[CorpusSource, ...]:
        return self._sources

    def sample(
        self, condition: Cell, n: int, seed: int, source: str | None = None
    ) -> list[Instance]:
        if n < 0:
            raise ValueError("sample size must be nonnegative")
        if source is not None and source not in self._items:
            raise ValueError("unknown corpus source")
        names = [source] if source is not None else sorted(self._items)
        rows = [Instance.model_validate_json(raw) for name in names for raw in self._items[name]]
        eligible = sorted((i for i in rows if i.cell.covers(condition)), key=lambda i: i.id)
        return random.Random(seed).sample(eligible, min(n, len(eligible)))

    def fingerprint(self) -> str:
        return self._fingerprint
