"""Executable orchestration against explicit doubles; no production boundary is claimed."""

import pytest

from adversary.core.model import Completion, CompletionRequest, LanguageModel, ModelInfo
from adversary.core.trajectory import Budget, Trajectory
from adversary.core.verify import Verdict, Verifier
from adversary.domain.contract import Environment, Reference, SolvabilityCertificate
from adversary.execution.store import EpisodeStore
from adversary.probe.executor import ConfinedPrograms, ProgramExecutor
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.search.proposer import ProposalError, Proposer
from domains.swe_agents.reference.solver import SweReference
from domains.swe_agents.runner import GroundedRunner, PairAdmission, PairEvidence, pair_binding
from tests.test_tier1_grounding import grounded  # noqa: F401


class ExecutorDouble(ConfinedPrograms):
    """Trusted authored fixture adapter, never presented as Linux confinement evidence."""

    def inspect(self, program, cell):
        if program.kind is ProgramKind.PERTURBATION:
            return {"channel": "observation", "clauses": ["rewrite"]}
        return {"kind": program.kind}

    def generate(self, program, cell, seed, config, n):
        return [self.instance.model_copy(update={"cell": cell, "seed": seed + 1000}) for _ in range(n)]


class ProposalDouble(Proposer):
    def propose(self, context):
        if self.error:
            raise self.error
        return self.draft


class ReferenceDouble(Reference):
    calls = 0
    wrong = False
    solvable = True

    def certify(self, instance):
        self.calls += 1
        return SolvabilityCertificate(
            instance_id="wrong" if self.wrong else instance.id,
            method="reference_run", clean_passed=self.solvable,
            perturbations=tuple(k for k, v in instance.cell.levels.items() if v == "on"),
            perturbed_runs=3, perturbed_passed=3, evidence="executed test double",
        )


class GateDouble(PairAdmission):
    calls = 0
    wrong = False

    def check(self, draft, instances):
        self.calls += 1
        return PairEvidence(
            binding="0" * 64 if self.wrong else pair_binding(draft, instances),
            channel_receipt="a" * 64, gold_invariance_receipt="b" * 64,
        )


class OracleDouble:
    def require_protected(self):
        pass


class ModelDouble(LanguageModel):
    @property
    def info(self):
        return ModelInfo(id="test-double", backend="test", license="restricted")

    def complete(self, request: CompletionRequest) -> Completion:
        raise AssertionError("environment double owns execution")


class EnvironmentDouble(Environment):
    closed = False

    def run(self, model, budget):
        return Trajectory(instance_id=self.instance.id, model_id=model.info.id, messages=())

    def close(self):
        self.closed = True


class VerifierDouble(Verifier):
    def verify(self, trajectory, oracle):
        return Verdict(passed=True)


@pytest.fixture
def rig(grounded, tmp_path, monkeypatch):  # noqa: F811
    builder, _, _, draft, instance = grounded
    # Source checks still run; execution is delegated only for these authored fixtures.
    draft = draft.model_copy(update={
        "generator": ProgramSource(kind="generator", entrypoint="G", source="class G: pass"),
        "verifier": ProgramSource(kind="verifier", entrypoint="V", source="class V: pass"),
    })
    executor = ExecutorDouble()
    executor.instance = instance
    proposer = ProposalDouble()
    proposer.draft, proposer.error = draft, None
    reference, gate = ReferenceDouble(), GateDouble()
    builder.final_oracle_factory = lambda instance: OracleDouble()
    builder.require_protected_oracle = True
    environments = []

    def build(instance):
        environment = EnvironmentDouble()
        environment.instance = instance
        environments.append(environment)
        return environment

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(builder, "verifier", lambda: VerifierDouble())
    runner = GroundedRunner(
        builder, proposer, reference, ModelDouble(), EpisodeStore(tmp_path),
        admission=gate, executor=executor, budget=Budget(max_steps=1),
    )
    return runner, proposer, reference, gate, environments, draft.seed.instance_id


def test_complete_chain_materializes_each_arm_and_builds_fresh_environments(rig):
    runner, _, reference, gate, environments, task = rig
    report = runner.run(task, 2)
    assert [a.status for a in report.attempts] == ["executed", "executed"]
    assert gate.calls == 2 and reference.calls == 4
    assert len(environments) == 4 and all(e.closed for e in environments)
    assert len({id(e) for e in environments}) == 4
    for attempt in report.attempts:
        assert [r.episodes[0].arm for r in attempt.reports] == ["control", "treatment"]
        assert all(r.episodes[0].probe_id == attempt.binding for r in attempt.reports)
    assert all(e.instance.spec.perturbation is not None for e in environments)


@pytest.mark.parametrize("missing", ["protection", "admission"])
def test_missing_production_gate_refuses_before_reference_or_target(rig, missing):
    runner, _, reference, gate, environments, task = rig
    if missing == "protection":
        runner.builder.final_oracle_factory = None
    else:
        runner.admission = None
    rows = runner.run(task, 2).attempts
    assert len(rows) == 2 and all(r.status == "unreached" and r.stage == missing for r in rows)
    assert reference.calls == 0 and not environments


@pytest.mark.parametrize("error,status", [(ProposalError("invalid"), "rejected"),
                                         (TimeoutError("down"), "unreached")])
def test_every_proposal_attempt_retained_without_model_failure(rig, error, status):
    runner, proposer, reference, _, environments, task = rig
    proposer.error = error
    rows = runner.run(task, 3).attempts
    assert len(rows) == 3 and all(r.status == status and not r.reports for r in rows)
    assert reference.calls == 0 and not environments


def test_wrong_pair_receipt_cannot_reach_reference(rig):
    runner, _, reference, gate, environments, task = rig
    gate.wrong = True
    row = runner.run(task, 1).attempts[0]
    assert row.stage == "admission" and row.status == "unreached"
    assert reference.calls == 0 and not environments


@pytest.mark.parametrize("wrong", [False, True])
def test_failed_or_misbound_reference_never_reaches_target(rig, wrong):
    runner, _, reference, _, environments, task = rig
    reference.wrong, reference.solvable = wrong, wrong
    row = runner.run(task, 1).attempts[0]
    assert row.status == ("unreached" if wrong else "witness_failed")
    assert not environments


def test_build_failure_retains_both_target_attempts(rig, monkeypatch):
    runner, _, _, _, _, task = rig
    def fail(instance):
        raise RuntimeError("allocation unavailable")
    monkeypatch.setattr(runner.builder, "build", fail)
    row = runner.run(task, 1).attempts[0]
    assert row.status == "executed"
    assert len(row.reports) == 2
    assert all(len(report.unreached) == 1 and not report.episodes for report in row.reports)


def test_unconfined_executor_is_not_a_production_option(rig):
    runner, proposer, reference, gate, _, _ = rig
    with pytest.raises(ValueError, match="confined"):
        GroundedRunner(runner.builder, proposer, reference, runner.target, runner.harness.store,
                       executor=ProgramExecutor(), admission=gate)


@pytest.mark.parametrize("error", [None, "broken worker"])
def test_unrealised_or_broken_reference_does_not_count_as_witness(rig, monkeypatch, error):
    runner, _, _, _, _, _ = rig
    instance = runner.executor.instance
    class NotRealised(EnvironmentDouble):
        def run(self, model, budget):
            return Trajectory(instance_id=instance.id, model_id=model.info.id, messages=(),
                              realised=False, error=error)
    monkeypatch.setattr(runner.builder, "build", lambda instance: NotRealised())
    reference = SweReference(runner.builder)
    if error:
        with pytest.raises(RuntimeError, match="broken worker"):
            reference._run(instance, runner.target, instance.oracle)
    else:
        assert reference._run(instance, runner.target, instance.oracle)[0] is False


def test_boolean_integer_configuration_change_is_not_a_matched_pair(rig, monkeypatch):
    runner, _, reference, gate, environments, task = rig
    generate = runner.executor.generate
    def changed(program, cell, seed, config, n):
        return [instance.model_copy(update={
            "perturbation_config": {"value": True if cell.levels.get("rewrite") == "off" else 1}
        }) for instance in generate(program, cell, seed, config, n)]
    monkeypatch.setattr(runner.executor, "generate", changed)
    row = runner.run(task, 1).attempts[0]
    assert row.stage == "generate" and row.status == "unreached"
    assert reference.calls == 0 and gate.calls == 0 and not environments


def test_unprotected_configured_oracle_refuses_before_proposal(rig, monkeypatch):
    runner, proposer, reference, _, environments, task = rig
    class Unprotected:
        def require_protected(self):
            raise RuntimeError("unprotected replay")
    runner.builder.final_oracle_factory = lambda instance: Unprotected()
    monkeypatch.setattr(proposer, "propose", lambda context: pytest.fail("spent proposal call"))
    row = runner.run(task, 1).attempts[0]
    assert row.stage == "protection" and row.status == "unreached"
    assert not environments and reference.calls == 0


def test_failed_attempt_receipts_identify_repeated_schedules(rig):
    runner, proposer, _, _, _, task = rig
    proposer.error = TimeoutError("down")
    first, second = runner.run(task, 1).attempts[0], runner.run(task, 1).attempts[0]
    assert first.run_id != second.run_id
    assert first.task_id == second.task_id == task
    assert first.planned_attempts == 1 and first.seed_index == 0
    assert len(runner.attempt_log.read_text().splitlines()) == 2
