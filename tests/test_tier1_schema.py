"""Strict schema and both-arm structural gate regressions; no model requests."""

import json

import pytest

from adversary.core.model import Message
from adversary.execution.backends.scripted import ScriptedModel
from adversary.probe.executor import ProgramExecutor
from adversary.search import critic as critic_module
from adversary.search.critic import CriticChain, LLMCritic, Reason, StaticCritic
from adversary.search.proposer import DRAFT_SCHEMA, ProposalError, parse_draft
from tests.test_pcode_contract import CONFIG, GEN, raw_draft


def critique_source(source):
    raw = raw_draft()
    raw["generator"]["source"] = source
    return StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(
        parse_draft(json.dumps(raw), None)
    )


def test_control_arm_crash_cannot_hide_behind_valid_treatment():
    result = critique_source(
        GEN.replace(
            "seed = self.next_seed()",
            "seed = self.next_seed()\n        if self.cell['rewrite'] == 'off': raise ValueError('control')",
        )
    )
    assert not result.accepted
    assert any("control" in objection.detail for objection in result.objections)


def test_control_arm_payload_drift_and_cell_mismatch_rejected():
    result = critique_source(
        GEN.replace(
            "spec=self.config['spec']",
            "spec=self.config['spec'] if self.cell['rewrite'] == 'on' else {'forged': 1}",
        )
    )
    assert not result.accepted
    assert any("trusted spec" in objection.detail for objection in result.objections)
    result = critique_source(GEN.replace("cell=self.cell", "cell=Cell(levels={'rewrite': 'on'})"))
    assert not result.accepted
    assert any("draft cell" in objection.detail for objection in result.objections)


def test_control_arm_full_payload_nondeterminism_rejected():
    source = GEN.replace(
        "resource=self.config",
        "perturbation_config={'n': random.random() if self.cell['rewrite'] == 'off' else 0},\n"
        "            resource=self.config",
    )
    result = critique_source(source)
    assert not result.accepted
    assert any(o.reason == Reason.NONDETERMINISM for o in result.objections)


def test_v2_defaults_to_confined_execution_before_source_load(monkeypatch):
    calls = []

    class RefusingWorker(ProgramExecutor):
        confined = True

        def inspect(self, program, cell):
            calls.append(program.kind)
            raise RuntimeError("confinement unavailable")

    monkeypatch.setattr(critic_module, "ConfinedPrograms", RefusingWorker)
    result = StaticCritic(generator_config=CONFIG).critique(
        parse_draft(json.dumps(raw_draft()), None)
    )
    assert calls and not result.accepted
    assert "confinement unavailable" in result.objections[0].detail


@pytest.mark.parametrize("program", ["generator", "perturbation", "verifier"])
def test_class_name_only_source_rejected_without_execution(program):
    raw = raw_draft()
    raw[program]["source"] = raw[program]["entrypoint"]
    result = StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(
        parse_draft(json.dumps(raw), None)
    )
    assert not result.accepted
    assert any("not a class" in o.detail for o in result.objections)


def test_bypassed_draft_validation_is_rechecked_by_critic():
    draft = parse_draft(json.dumps(raw_draft()), None)
    invalid = draft.model_copy(update={"clauses": ("other",)})
    result = StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(invalid)
    assert not result.accepted
    assert "every declared clause" in result.objections[0].detail


@pytest.mark.parametrize("timestamp", ["42", 42.0, True])
def test_seed_echo_cannot_coerce_timestamp(timestamp):
    raw = raw_draft()
    raw["seed"]["ts"] = timestamp
    with pytest.raises(ProposalError, match="without coercion"):
        parse_draft(json.dumps(raw), None)


def test_schema_retains_construction_contract_and_literal_newline_guidance():
    assert r"escaped as \n." in DRAFT_SCHEMA
    for signature in (
        "def __next__(self)",
        "def prepare(self, session, spec)",
        "def observe(self, step: int",
        "def verify(self, trajectory:",
        "self.rng: random.Random",
        "These names are already bound",
    ):
        assert signature in DRAFT_SCHEMA


@pytest.mark.parametrize("reply", ["", "Probably fine", "OK but change the oracle", "null"])
def test_critic_unrecognized_responses_reject(reply):
    model = ScriptedModel(lambda request: Message(role="assistant", content=reply))
    critic = LLMCritic(model)
    assert not critic.critique(parse_draft(json.dumps(raw_draft()), None)).accepted
    with pytest.raises(ValueError, match="StaticCritic"):
        CriticChain([critic])
