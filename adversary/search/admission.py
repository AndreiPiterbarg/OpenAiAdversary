"""Finite admission queue with evidence addresses and versioned history."""

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.util import sha256_json
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.search.context import MinedSeed


class CandidateOperator(FrozenModel):
    id: str = Field(min_length=1)
    program: ProgramSource
    seed: MinedSeed


class AdmissionEvidence(FrozenModel):
    """External gate receipts, not a model's assertion of validity."""

    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    singleton_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")
    channel_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")


class OperatorRegister:
    """One decision per candidate; admissions increment the register version.

    Effect evidence follows the registered protocol without requiring a retired panel.
    This register records gate decisions; it does not manufacture their evidence.
    """

    def __init__(self) -> None:
        self.version = 0
        self.pending: dict[str, CandidateOperator] = {}
        self.admitted: dict[str, CandidateOperator] = {}
        self.history: list[dict] = []

    def nominate(self, candidate: CandidateOperator) -> None:
        if candidate.program.kind is not ProgramKind.PERTURBATION:
            raise ValueError("operator candidate requires an executable perturbation")
        if any(row["id"] == candidate.id for row in self.history) or candidate.id in self.pending:
            raise ValueError("candidate already queued or decided")
        self.pending[candidate.id] = candidate

    def admit(self, candidate_id: str, evidence: AdmissionEvidence) -> None:
        candidate = self.pending.pop(candidate_id)
        self.admitted[candidate_id] = candidate
        self.version += 1
        self.history.append(
            {
                "id": candidate_id,
                "version": self.version,
                "decision": "admitted",
                "evidence": evidence.model_dump(),
            }
        )

    def reject(self, candidate_id: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("rejection requires a reason")
        self.pending.pop(candidate_id)
        self.history.append(
            {"id": candidate_id, "version": self.version, "decision": "rejected", "reason": reason}
        )

    def fingerprint(self) -> str:
        return sha256_json(
            {
                "version": self.version,
                "history": self.history,
                "admitted": {
                    k: v.model_dump(mode="json") for k, v in sorted(self.admitted.items())
                },
            }
        )
