"""Exact realisability under forbidden partial assignments.

An envelope's exclusions, plus any run-time constraints such as a task pool's empty pattern
cells, are *forbidden sets*: partial assignments that must never all hold. A partial cell is
*realisable* if some full assignment of the varied factors extends it without completing any
forbidden set. One-step lookahead misses chains (``a`` forces ``b`` forces ``c``, and ``c`` is
forbidden with something already assigned), so realisability is decided by a backtracking
search over the factors that appear in any forbidden set. Factors no forbidden set mentions
are always completable and are never searched. Results are memoised on the cell's projection
onto the constrained factors, which is all realisability depends on, so a full-envelope
classification at strength 3 costs a dictionary lookup per combination.
"""

from collections.abc import Iterable, Mapping, Sequence

from adversary.core.factors import Atom, Cell, Factor


class Forbidden:
    """A set of forbidden partial assignments over declared factors, with a realisability oracle."""

    def __init__(
        self,
        factors: Sequence[Factor],
        forbidden: Iterable[Cell],
        pinned: Mapping[str, str] | None = None,
    ) -> None:
        self.levels: dict[str, tuple[str, ...]] = {f.name: f.levels for f in factors}
        self.pinned: dict[str, str] = dict(pinned or {})
        self.sets: tuple[tuple[Atom, ...], ...] = tuple(c.atoms for c in forbidden)
        self._by_atom: dict[Atom, list[tuple[Atom, ...]]] = {}
        for forbidden_set in self.sets:
            for atom in forbidden_set:
                self._by_atom.setdefault(atom, []).append(forbidden_set)
        self.constrained: tuple[str, ...] = tuple(
            sorted({atom[0] for forbidden_set in self.sets for atom in forbidden_set})
        )
        self._searchable: tuple[str, ...] = tuple(
            f for f in self.constrained if f not in self.pinned and f in self.levels
        )
        self._cache: dict[tuple[Atom, ...], bool] = {}

    # -- primitives --------------------------------------------------------------------------

    def with_pinned(self, levels: Mapping[str, str]) -> dict[str, str] | None:
        """Merge the pinned levels in; ``None`` if ``levels`` contradicts a pinned factor."""
        merged = dict(self.pinned)
        for factor, level in levels.items():
            if merged.get(factor, level) != level:
                return None
            merged[factor] = level
        return merged

    def violates(self, assigned: Mapping[str, str]) -> bool:
        """Whether some forbidden set is fully contained in ``assigned``."""
        return any(
            all(assigned.get(f) == lv for f, lv in forbidden_set) for forbidden_set in self.sets
        )

    def completes(self, assigned: Mapping[str, str], atom: Atom) -> bool:
        """Whether adding ``atom`` to ``assigned`` completes some forbidden set."""
        for forbidden_set in self._by_atom.get(atom, ()):
            if all(o == atom or assigned.get(o[0]) == o[1] for o in forbidden_set):
                return True
        return False

    # -- realisability -----------------------------------------------------------------------

    def feasible(self, levels: Mapping[str, str]) -> bool:
        """Pinned levels respected and no forbidden set completed."""
        merged = self.with_pinned(levels)
        return merged is not None and not self.violates(merged)

    def realisable(self, levels: Mapping[str, str]) -> bool:
        """Whether some full assignment extends ``levels`` without completing a forbidden set."""
        merged = self.with_pinned(levels)
        if merged is None or self.violates(merged):
            return False
        key = tuple(sorted((f, lv) for f, lv in merged.items() if f in self._by_atom_factors()))
        cached = self._cache.get(key)
        if cached is None:
            assigned = dict(key)
            open_factors = [f for f in self._searchable if f not in assigned]
            open_factors.sort(key=lambda f: len(self.levels[f]))
            cached = self._search(assigned, open_factors, 0)
            self._cache[key] = cached
        return cached

    def _by_atom_factors(self) -> frozenset[str]:
        return frozenset(self.constrained)

    def _search(self, assigned: dict[str, str], open_factors: list[str], depth: int) -> bool:
        if depth == len(open_factors):
            return True
        factor = open_factors[depth]
        for level in self.levels[factor]:
            if self.completes(assigned, (factor, level)):
                continue
            assigned[factor] = level
            if self._search(assigned, open_factors, depth + 1):
                del assigned[factor]
                return True
            del assigned[factor]
        return False
