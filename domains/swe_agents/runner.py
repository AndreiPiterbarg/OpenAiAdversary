"""Grounded discovery orchestration with explicit admission and all-attempt receipts.

This runs a fresh minimal pair, not confirmation or a mode claim. The production
runtime still cannot supply a protected final oracle; that missing capability refuses
before reference or target calls. Injected gate implementations are trusted harness
code, never proposer-returned receipt strings.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from adversary.core.model import LanguageModel, TargetPin
from adversary.core.trajectory import Budget
from adversary.core.util import canonical_json, sha256_json, short_id
from adversary.domain.contract import Reference, SolvabilityCertificate
from adversary.execution.harness import Harness, RunReport
from adversary.execution.store import EpisodeStore
from adversary.probe.executor import ConfinedPrograms
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.search.critic import StaticCritic
from adversary.search.draft import ProbeDraft
from adversary.search.proposer import ProposalError, Proposer
from domains.swe_agents.environment.builder import SweEnvironmentBuilder


class PairEvidence(FrozenModel):
    """Addresses emitted by a trusted executable gate, bound to the entire pair."""

    binding: str = Field(pattern=r"^[0-9a-f]{64}$")
    channel_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_invariance_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")


def pair_binding(draft: ProbeDraft, instances: tuple[Instance, Instance]) -> str:
    # Include hidden tests, gold, image, seed, program and per-arm configurations.
    return sha256_json({
        "draft": draft.model_dump(mode="json"),
        "instances": [instance.model_dump(mode="json") for instance in instances],
    })


class PairAdmission(ABC):
    """Trusted execution of channel/build/gold-clean versus gold-perturbed checks.

    Implementations must run fresh sessions and persist the underlying receipts.
    No production implementation is supplied until protected evaluation is available.
    """

    @abstractmethod
    def check(self, draft: ProbeDraft, instances: tuple[Instance, Instance]) -> PairEvidence:
        """Raise on missing/failed gates; return addresses only for completed checks."""


class GroundedAttempt(FrozenModel):
    run_id: str = ""
    task_id: str = ""
    seed_index: int = 0
    planned_attempts: int = 0
    index: int
    stage: str
    status: Literal["rejected", "unreached", "witness_failed", "executed"]
    reason: str = ""
    binding: str | None = None
    admission: PairEvidence | None = None
    certificates: tuple[SolvabilityCertificate, ...] = ()
    reports: tuple[RunReport, ...] = ()


class GroundedRun(FrozenModel):
    """No admission, effect, or failure rate silently conditions away missing attempts."""

    attempts: tuple[GroundedAttempt, ...]


class GroundedRunner:
    """One fixed sequence of proposal attempts, each with a fresh generated pair."""

    def __init__(
        self,
        builder: SweEnvironmentBuilder,
        proposer: Proposer,
        reference: Reference,
        target: LanguageModel,
        store: EpisodeStore,
        *,
        admission: PairAdmission | None = None,
        executor: ConfinedPrograms | None = None,
        budget: Budget | None = None,
        target_pin: TargetPin | None = None,
    ) -> None:
        self.builder, self.proposer, self.reference = builder, proposer, reference
        self.target, self.admission = target, admission
        self.attempt_log = store.directory / "grounded-attempts.jsonl"
        self.executor = executor or ConfinedPrograms()
        if not isinstance(self.executor, ConfinedPrograms):
            raise ValueError("model-authored generation requires a confined executor")
        self.harness = Harness(builder, store, budget=budget, target_pin=target_pin)

    def run(self, task_id: str, attempts: int, *, seed_index: int = 0) -> GroundedRun:
        if type(attempts) is not int or attempts < 1:
            raise ValueError("attempts must be a positive integer")
        rows = []
        run_id = short_id("grounded")
        for index in range(attempts):
            row = self._attempt(task_id, seed_index, index).model_copy(update={
                "run_id": run_id, "task_id": task_id, "seed_index": seed_index,
                "planned_attempts": attempts,
            })
            with self.attempt_log.open("a", encoding="utf-8") as handle:
                handle.write(row.model_dump_json() + "\n")
            rows.append(row)
        return GroundedRun(attempts=tuple(rows))

    def _attempt(self, task_id: str, seed_index: int, index: int) -> GroundedAttempt:
        stage = "inputs"
        certificates: list[SolvabilityCertificate] = []
        reports: list[RunReport] = []
        evidence = None
        binding = None
        try:
            context, config = self.builder.proposal_inputs(task_id, seed_index)
            stage = "protection"
            if (not self.builder.require_protected_oracle
                    or self.builder.final_oracle_factory is None):
                raise ValueError("grounded execution requires a protected final oracle")
            baseline = Instance(
                id="oracle-preflight", cell=Cell(levels={}), seed=0,
                spec=config["spec"], oracle=config["oracle"], resource=config["resource"],
                provenance=Provenance(generator="trusted-preflight", generator_version="1",
                                      seed=0, source_license=config["source_license"]),
            )
            self.builder.require_protected(baseline)
            stage = "admission"
            if self.admission is None:
                raise ValueError("trusted channel/build/gold invariance gate is unavailable")
            stage = "execution_preflight"
            self.harness._validate_target_pin(self.target)
            if self.harness.budget.max_tokens is not None:
                raise ValueError("finite total token accounting is unavailable")
            fixture = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint="G", source="""
class G(Generator):
    def __next__(self):
        return Instance(id='preflight', cell=self.cell, seed=0,
                        spec=self.config['spec'], oracle=self.config['oracle'],
                        provenance=Provenance(generator='G', generator_version='1', seed=0))
""")
            self.executor.inspect(fixture, Cell(levels={}))
            self.executor.generate(fixture, Cell(levels={}), 0, deepcopy(config), 1)
            stage = "propose"
            draft = self.proposer.propose(context)
            if draft.seed != context.mined_seed or draft.perturbation is None:
                raise ProposalError("proposal must preserve the selected mined seed and v2 shape")
            stage = "critique"
            critique = StaticCritic(executor=self.executor, generator_config=config).critique(draft)
            if not critique.accepted:
                return GroundedAttempt(
                    index=index, stage=stage, status="rejected",
                    reason="; ".join(o.detail for o in critique.objections),
                )
            stage = "generate"
            generated = []
            for cell in (draft.pair.control, draft.pair.treatment):
                batch = self.executor.generate(draft.generator, cell, index, deepcopy(config), 1)
                if len(batch) != 1 or batch[0].cell != cell:
                    raise ValueError("generated arm does not match its requested cell")
                generated.append(self.builder.materialize(draft, batch[0]))
            instances = (generated[0], generated[1])
            if _paired_payload(instances[0]) != _paired_payload(instances[1]):
                raise ValueError("minimal pair changed configuration beyond its declared switch")
            binding = pair_binding(draft, instances)
            stage = "protection"
            for instance in instances:
                self.builder.require_protected(instance)
            stage = "admission"
            if self.admission is None:
                raise ValueError("trusted channel/build/gold invariance gate is unavailable")
            evidence = self.admission.check(draft, instances)
            if evidence.binding != binding or pair_binding(draft, instances) != binding:
                raise ValueError("admission evidence or mutated input differs from the frozen pair")
            stage = "reference"
            for instance in instances:
                certificate = self.reference.certify(instance)
                certificates.append(certificate)
                active = tuple(k for k, v in instance.cell.levels.items() if v == "on")
                if certificate.instance_id != instance.id or certificate.perturbations != active:
                    raise ValueError("reference certificate differs from the executed arm")
                if not certificate.solvable:
                    return GroundedAttempt(
                        index=index, stage=stage, status="witness_failed", binding=binding,
                        admission=evidence, certificates=tuple(certificates),
                        reason="reference or recovery witness did not establish solvability",
                    )
            if pair_binding(draft, instances) != binding:
                raise ValueError("reference changed the admitted pair")
            stage = "target"
            for arm, instance in zip(("control", "treatment"), instances, strict=True):
                reports.append(self.harness.run(
                    (instance,), self.target, probe_id=binding, arm=arm,
                ))
            return GroundedAttempt(
                index=index, stage=stage, status="executed", binding=binding,
                admission=evidence, certificates=tuple(certificates), reports=tuple(reports),
                reason="fresh target attempts recorded; inspect unreached and unrealised rows",
            )
        except Exception as exc:  # noqa: BLE001 - every scheduled attempt retains its outcome
            return GroundedAttempt(
                index=index, stage=stage,
                status="rejected" if isinstance(exc, ProposalError) else "unreached",
                reason=repr(exc), binding=binding, admission=evidence,
                certificates=tuple(certificates), reports=tuple(reports),
            )


def _paired_payload(instance: Instance) -> str:
    """Only arm identity and its declared switch may differ in a matched pair."""
    payload = instance.model_dump(mode="json")
    payload.pop("id")
    payload.pop("cell")
    payload["spec"].pop("clause_cell")
    payload["provenance"].pop("created_at", None)
    return canonical_json(payload)
