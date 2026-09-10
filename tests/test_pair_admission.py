"""Admission orchestration doubles are not evidence of a protected cluster runtime."""

import json
from types import SimpleNamespace

import pytest

from adversary.core.util import sha256_json
from adversary.probe.observation import IsolatedObservation
from domains.swe_agents import pair_admission as module
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from domains.swe_agents.environment.spec import SweOracle, SweTaskSpec
from tests.test_tier1_grounding import grounded  # noqa: F401


class ObserverDouble(IsolatedObservation):
    def __init__(self):
        self.prepared = False

    def prepare(self, session, spec):
        assert session is None and "pin" not in spec
        self.prepared = True


class OracleDouble:
    def require_protected(self):
        pass

    def evaluate(self, session):
        assert session.applied
        return {"test_results": {"exit": 0, "stdout": "tests/test_x.py::test_a PASSED\n"},
                "changed_files": session.changed}


class SessionDouble:
    applied = False
    changed = ()

    def exec(self, command, timeout):
        if command.startswith("mktemp"):
            return 0, "/tmp/pcode-gold-1234", ""
        if command.startswith("git apply -- "):
            self.applied = True
        return 0, "", ""

    def write_file(self, path, data):
        assert data


class EnvironmentDouble:
    def __init__(self, instance):
        self.session = SessionDouble()
        self.spec = SweTaskSpec.model_validate(instance.spec)
        self.oracle = SweOracle.model_validate(instance.oracle).model_copy(update={
            "gold_patch": "controlled patch", "fail_to_pass": ("tests/test_x.py::test_a",),
            "pass_to_pass": (),
        })
        self.perturbation = ObserverDouble()
        self.final_oracle = OracleDouble()
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


@pytest.fixture
def gate_rig(grounded, tmp_path, monkeypatch):  # noqa: F811
    builder, _, _, draft, instance = grounded
    instances = tuple(builder.materialize(draft, instance.model_copy(update={"cell": cell}))
                      for cell in (draft.pair.control, draft.pair.treatment))
    # Only receipt parsing is substituted here; its real hash/raw-evidence validation
    # has independent prun receipt tests. No fabricated manifests enter production.
    monkeypatch.setattr(module, "load_prun_receipt", lambda *args: (builder.pool.pins, {}))
    environments = []

    def build(item):
        env = EnvironmentDouble(item)
        environments.append(env)
        return env

    trusted_double = SimpleNamespace(
        build=build, require_protected=lambda item: None, materialize=builder.materialize,
    )
    gate = module.ObservationPairAdmission(
        trusted_double, task_receipts=tmp_path / "task", trusted_manifest_sha256="a" * 64,
        corpus="discovery_149", receipts=tmp_path / "out",
    )
    return gate, draft, instances, environments


def test_actual_gate_persists_bound_full_evidence(gate_rig):
    gate, draft, instances, environments = gate_rig
    result = gate.check(draft, instances)
    for address in (result.channel_receipt, result.gold_invariance_receipt):
        record = json.loads((gate.receipts / (address + ".json")).read_text())
        assert sha256_json(record) == address
        assert record["binding"] == module.pair_binding(draft, instances)
    assert len(environments) == 2
    assert all(e.closed and e.perturbation.prepared for e in environments)


def test_anchor_errors_propagate_before_build(gate_rig, monkeypatch):
    gate, draft, instances, envs = gate_rig

    def invalid(*args):
        raise ValueError("root manifest digest mismatch")

    monkeypatch.setattr(module, "load_prun_receipt", invalid)
    with pytest.raises(ValueError, match="manifest"):
        gate.check(draft, instances)
    assert not envs


def test_missing_protection_refuses_before_build(gate_rig):
    gate, draft, instances, envs = gate_rig

    def unavailable(instance):
        raise RuntimeUnavailable("no protected evaluator")

    gate.builder.require_protected = unavailable
    with pytest.raises(RuntimeUnavailable):
        gate.check(draft, instances)
    assert not envs and not gate.receipts.exists()


def test_full_verdict_notes_difference_is_not_invariance(gate_rig):
    gate, draft, instances, envs = gate_rig
    original = gate.builder.build

    def build(item):
        env = original(item)
        env.session.changed = ("changed.py",) if len(envs) == 2 else ()
        return env

    gate.builder.build = build
    with pytest.raises(ValueError, match="verdicts differ"):
        gate.check(draft, instances)
    assert all(e.closed for e in envs)
    assert not gate.receipts.exists()


def test_failing_gold_is_not_successful_invariance(gate_rig, monkeypatch):
    gate, draft, instances, envs = gate_rig
    monkeypatch.setattr(OracleDouble, "evaluate", lambda *args: {
        "test_results": {"exit": 1, "stdout": "tests/test_x.py::test_a FAILED\n"}})
    with pytest.raises(ValueError, match="did not pass"):
        gate.check(draft, instances)
    assert len(envs) == 1 and envs[0].closed
    assert not gate.receipts.exists()


def test_wrong_arm_refused(gate_rig):
    gate, draft, instances, envs = gate_rig
    with pytest.raises(ValueError, match="arm differs"):
        gate.check(draft, (instances[1], instances[0]))
    assert not envs


def test_modified_hidden_oracle_refused_before_build(gate_rig):
    gate, draft, instances, envs = gate_rig
    oracle = SweOracle.model_validate(instances[0].oracle).model_copy(update={
        "expected_packages": {"invented": "1"},
    })
    altered = tuple(i.model_copy(update={"oracle": oracle}) for i in instances)
    with pytest.raises(ValueError, match="trusted grounded inputs"):
        gate.check(draft, altered)
    assert not envs


def test_reused_arm_session_refused(gate_rig):
    gate, draft, instances, envs = gate_rig
    original = gate.builder.build

    def build(item):
        env = original(item)
        if len(envs) == 2:
            env.session = envs[0].session
        return env

    gate.builder.build = build
    with pytest.raises(ValueError, match="reused"):
        gate.check(draft, instances)
    assert len(envs) == 2 and all(e.closed for e in envs)
    assert not gate.receipts.exists()


def test_oracle_infrastructure_error_cleans_up(gate_rig, monkeypatch):
    gate, draft, instances, envs = gate_rig

    def unavailable(*args):
        raise RuntimeUnavailable("evaluator disconnected")

    monkeypatch.setattr(OracleDouble, "evaluate", unavailable)
    with pytest.raises(RuntimeUnavailable, match="disconnected"):
        gate.check(draft, instances)
    assert len(envs) == 1 and envs[0].closed
    assert not gate.receipts.exists()


def test_mutated_pair_never_gets_receipt(gate_rig, monkeypatch):
    gate, draft, instances, envs = gate_rig
    original = OracleDouble.evaluate

    def mutate(self, session):
        if len(envs) == 2:
            instances[0].perturbation_config["tampered"] = True
        return original(self, session)

    monkeypatch.setattr(OracleDouble, "evaluate", mutate)
    with pytest.raises(ValueError, match="mutated"):
        gate.check(draft, instances)
    assert all(e.closed for e in envs)
    assert not gate.receipts.exists()


def test_active_control_is_not_clean_gold(gate_rig):
    from adversary.core.factors import Cell
    from adversary.probe.kill import MinimalPair

    gate, draft, instances, envs = gate_rig
    raw = draft.model_dump()
    raw["clauses"] = ("rewrite", "second")
    raw["cell"] = Cell(levels={"rewrite": "on", "second": "on"})
    raw["pair"] = MinimalPair(
        control=Cell(levels={"rewrite": "on", "second": "off"}),
        treatment=raw["cell"],
    )
    draft = type(draft).model_validate(raw)
    altered = tuple(i.model_copy(update={"cell": cell})
                    for i, cell in zip(
                        instances, (draft.pair.control, draft.pair.treatment), strict=True
                    ))
    with pytest.raises(ValueError, match="all-off"):
        gate.check(draft, altered)
    assert not envs
