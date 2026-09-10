"""The confirmatory excess: the rate-scale Möbius decomposition over injected factors.

Amendment A5 separates two roles. The *screening* statistic for hot cells is the logistic
residual in :mod:`adversary.stats.excess`. The *confirmatory* excess for any cell that enters
a region claim, the region test or a shipped mode is the rate-scale Möbius sum over the
injected factors, estimated by the branch design: from each instance's first-injection
snapshot, every subset of the injected factors is run and the failure rates pooled.

For subset failure rates ``p(S)``, the Möbius transform is::

    m(S) = sum over T subset of S of (-1)^(|S| - |T|) p(T)

``m({i})`` is factor i's main effect over the empty subset, and terms of order two and above
are interactions. The *synergy* is the sum of all terms of order at least two, which equals
``p(full) - p(empty) - sum_i m({i})``: the rate-scale excess over additive main effects. Under
monotonicity (no injected factor is protective) a positive pair term has a causal reading from
sufficient-component-cause epidemiology.
"""

from collections.abc import Mapping
from itertools import combinations

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.util import canonical_json
from adversary.stats.clauses import ClauseAudit

Subset = frozenset[str]


def _subsets(factors: tuple[str, ...]) -> list[Subset]:
    return [frozenset(c) for r in range(len(factors) + 1) for c in combinations(factors, r)]


class MobiusSynergy(FrozenModel):
    """Möbius terms of a cell's injected factors and the derived confirmatory excess."""

    factors: tuple[str, ...]
    rates: dict[str, float] = Field(description="JSON-encoded sorted subset -> pooled failure rate")
    terms: dict[str, float] = Field(description="JSON-encoded sorted subset -> Möbius term")
    synergy: float = Field(description="Sum of terms of order >= 2, in probability")
    highest_order_term: float = Field(description="The pure term of the full subset")
    n_per_subset: dict[str, int] = Field(default_factory=dict)

    @property
    def synergy_points(self) -> float:
        return 100.0 * self.synergy


def _key(subset: Subset) -> str:
    return canonical_json(sorted(subset))


def mobius_synergy(
    factors: tuple[str, ...],
    rates: Mapping[Subset, float],
    n_per_subset: Mapping[Subset, int] | None = None,
    *,
    clause_audit: ClauseAudit | None = None,
    program_digest: str | None = None,
) -> MobiusSynergy:
    """Decompose subset failure rates into Möbius terms and report the confirmatory excess.

    Args:
        factors: The reviewed switches, with no arbitrary decomposition-order cap.
        rates: Failure rate of every subset of ``factors``, the empty subset included.
        n_per_subset: Episodes behind each rate, for the record.
    """
    if not factors or len(set(factors)) != len(factors):
        raise ValueError("distinct nonempty switches required")
    if clause_audit is None:
        raise ValueError("excess refused: independent clause-declaration audit is missing")
    clause_audit.require(factors, program_digest)
    if any(not 0 <= value <= 1 for value in rates.values()):
        raise ValueError("subset rates must be finite probabilities")
    subsets = _subsets(factors)
    missing = [s for s in subsets if s not in rates]
    if missing:
        raise ValueError(f"missing subset rates: {[_key(s) for s in missing]}")
    terms: dict[Subset, float] = {}
    for s in subsets:
        terms[s] = sum(((-1) ** (len(s) - len(t))) * rates[t] for t in subsets if t <= s)
    synergy = sum(v for s, v in terms.items() if len(s) >= 2)
    full = frozenset(factors)
    return MobiusSynergy(
        factors=factors,
        rates={_key(s): float(rates[s]) for s in subsets},
        terms={_key(s): float(v) for s, v in terms.items()},
        synergy=float(synergy),
        highest_order_term=float(terms[full]),
        n_per_subset={_key(s): int(n) for s, n in (n_per_subset or {}).items()},
    )


class BranchAgreement(FrozenModel):
    """Precondition of the branch design: snapshot-and-resume must agree with fresh runs."""

    branch_rate: float
    fresh_rate: float
    tolerance: float
    valid: bool = Field(description="|branch - fresh| <= tolerance; else subsets run from scratch")


def branch_agreement(
    branch_rate: float, fresh_rate: float, tolerance: float = 0.10
) -> BranchAgreement:
    """Test the branch estimator against a fresh-run estimate of the same full cell."""
    return BranchAgreement(
        branch_rate=branch_rate,
        fresh_rate=fresh_rate,
        tolerance=tolerance,
        valid=bool(abs(branch_rate - fresh_rate) <= tolerance),
    )
