"""The referee: the solvability floor.

Unsolvable items fail 100% of the time, so an unrefereed adversary manufactures them. Every
admitted probe must show that a reference solves its instances clean, and, with perturbations
present, that a recovery witness solves them on every required run (Amendment A3). The
*floor gap*, the fraction of perturbed instances that pass clean and fail perturbed, is
reported per perturbation label as a bounded witness-search failure rate,
not proof of impossibility.
"""

import math
from collections import defaultdict
from collections.abc import Sequence

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.instance import Instance
from adversary.domain.contract import Reference, SolvabilityCertificate


class RefereeReport(FrozenModel):
    """Certificates for a sample of instances and the admission decision."""

    certificates: tuple[SolvabilityCertificate, ...]
    min_solvable_fraction: float
    unavailable: int = Field(default=0, ge=0, description="Missing or invalid certificates")
    admitted: bool = Field(description="True if enough instances were certified solvable")
    floor_gap: dict[str, float] = Field(
        default_factory=dict,
        description="Perturbation label -> share of its instances passing clean, failing perturbed",
    )

    @property
    def solvable_fraction(self) -> float:
        if not self.certificates:
            return 0.0
        return sum(1 for c in self.certificates if c.solvable) / len(self.certificates)

    @property
    def unrecoverable(self) -> int:
        return sum(1 for c in self.certificates if c.unrecoverable)

    @property
    def witness_failed(self) -> int:
        return sum(c.witness_failed for c in self.certificates)


def floor_gap(certificates: Sequence[SolvabilityCertificate]) -> dict[str, float]:
    """Per perturbation label, the share of certificates carrying it that are unrecoverable."""
    seen: dict[str, int] = defaultdict(int)
    gaps: dict[str, int] = defaultdict(int)
    for c in certificates:
        for label in c.perturbations:
            seen[label] += 1
            if c.witness_failed:
                gaps[label] += 1
    return {label: gaps[label] / seen[label] for label in sorted(seen)}


class Referee:
    """Applies the plugin's :class:`~adversary.domain.contract.Reference` to a sample."""

    def __init__(self, reference: Reference, min_solvable_fraction: float = 0.9) -> None:
        if (
            isinstance(min_solvable_fraction, bool)
            or not math.isfinite(min_solvable_fraction)
            or not 0 < min_solvable_fraction <= 1
        ):
            raise ValueError("min_solvable_fraction must be finite and in (0, 1]")
        self.reference = reference
        self.min_solvable_fraction = min_solvable_fraction

    def admit(self, instances: Sequence[Instance]) -> RefereeReport:
        """Certify each instance and decide."""
        certificates_list = []
        unavailable = 0
        for instance in instances:
            active = {key for key, level in instance.cell.levels.items() if level == "on"}
            try:
                certificate = self.reference.certify(instance)
                certificate = SolvabilityCertificate.model_validate(
                    certificate.model_dump(warnings=False)
                )
                if certificate.instance_id != instance.id:
                    raise ValueError("certificate belongs to another instance")
                if not active.issubset(certificate.perturbations):
                    raise ValueError("certificate omits active intervention witnesses")
            except Exception as exc:
                unavailable += 1
                certificate = SolvabilityCertificate(
                    instance_id=instance.id,
                    method="reference_run",
                    clean_passed=False,
                    perturbations=tuple(sorted(active)),
                    evidence=f"reference certificate unavailable: {type(exc).__name__}: {exc}",
                )
            certificates_list.append(certificate)
        certificates = tuple(certificates_list)
        solvable = (
            sum(1 for c in certificates if c.solvable) / len(certificates) if certificates else 0.0
        )
        return RefereeReport(
            certificates=certificates,
            unavailable=unavailable,
            min_solvable_fraction=self.min_solvable_fraction,
            admitted=bool(certificates) and solvable >= self.min_solvable_fraction,
            floor_gap=floor_gap(certificates),
        )
