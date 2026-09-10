"""Tier 1 bindings are checked before any task allocation."""

import json
from copy import deepcopy

import pytest

from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from adversary.probe.executor import ConfinedPrograms
from adversary.probe.kill import MinimalPair, Prediction
from adversary.probe.program import PROGRAM_NAMESPACE, ProgramError, ProgramKind, ProgramSource
from adversary.search.admission import OperatorRegister
from adversary.search.context import MinedSeed
from adversary.search.draft import ProbeDraft
from adversary.search.proposer import render_context
from domains.swe_agents.environment.builder import SweEnvironmentBuilder
from domains.swe_agents.environment.generator import TaskPool
from domains.swe_agents.mining.store import SeedStore
from tests.test_observation import program
from tests.test_swe_builder_explicit import setup


@pytest.fixture
def grounded():
    original, runtime, _ = setup()
    pin = original.spec.pin.model_copy(
        update={"commit": "a" * 40, "verification_receipt": "b" * 64}
    )
    seed = MinedSeed(
        instance_id=pin.key,
        repo=pin.repo,
        base_commit=pin.commit,
        miner="history",
        sha="c" * 40,
        ts=1,
        subject="actual historical change",
    )
    builder = SweEnvironmentBuilder(
        runtime=runtime,
        pool=TaskPool(pins=(pin,)),
        registry=OperatorRegister(),
        seed_store=SeedStore(records=(seed,), digest="fixture"),
    )
    context, config = builder.proposal_inputs(pin.key)
    draft = ProbeDraft(
        hypothesis="Observation changes alter decisions",
        seed=seed,
        generator=ProgramSource(kind=ProgramKind.GENERATOR, entrypoint="G", source="class G: pass"),
        verifier=ProgramSource(kind=ProgramKind.VERIFIER, entrypoint="V", source="class V: pass"),
        perturbation=program("return result"),
        channel="observation",
        clauses=("rewrite",),
        cell=Cell(levels={"rewrite": "on"}),
        pair=MinimalPair(
            control=Cell(levels={"rewrite": "off"}), treatment=Cell(levels={"rewrite": "on"})
        ),
        prediction=Prediction(min_effect=0.1, statement="More failures"),
    )
    instance = Instance(
        id="i",
        cell=draft.cell,
        seed=13,
        spec=config["spec"],
        oracle=config["oracle"],
        resource=config["resource"],
        perturbation_config={"nested": [1, {"suffix": "text"}]},
        provenance=Provenance(
            generator="G", generator_version="1", seed=13, source_license=config["source_license"]
        ),
    )
    return builder, runtime, context, draft, instance


def test_actual_harvest_fields_reach_prompt_without_hidden_inputs(grounded):
    builder, runtime, context, _, instance = grounded
    rendered = render_context(context)
    for name, value in context.mined_seed.model_dump().items():
        assert json.dumps(name) in rendered
        assert str(value) in rendered
    assert "gold_patch" not in rendered and "test_command" not in rendered
    assert instance.spec["pin"]["commit"] == context.mined_seed.base_commit
    with pytest.raises(ValueError, match="absent"):
        builder.proposal_inputs("unknown")
    assert not runtime.calls


@pytest.mark.parametrize("arm", ["control", "treatment"])
def test_both_arms_preserve_full_configuration_and_grounded_task(grounded, arm):
    builder, runtime, _, draft, instance = grounded
    instance = instance.model_copy(update={"cell": getattr(draft.pair, arm)})
    result = builder.materialize(draft, instance)
    assert result.spec.clause_cell == instance.cell
    assert result.spec.pin.model_dump(mode="json") == instance.spec["pin"]
    assert result.oracle == instance.oracle
    assert result.perturbation_config == instance.perturbation_config
    assert result.spec.perturbation == draft.perturbation
    assert not runtime.calls


@pytest.mark.parametrize("field", ["spec", "oracle", "resource", "license", "cell"])
def test_changed_grounded_input_refused_before_allocation(grounded, field):
    builder, runtime, _, draft, instance = grounded
    if field in ("spec", "oracle"):
        payload = deepcopy(getattr(instance, field))
        payload["step_budget" if field == "spec" else "test_command"] = (
            1 if field == "spec" else "true"
        )
        change = {field: payload}
    elif field == "license":
        change = {"provenance": instance.provenance.model_copy(update={"source_license": "MIT"})}
    elif field == "cell":
        change = {"cell": Cell(levels={"rewrite": "invented"})}
    else:
        change = {"resource": "different"}
    with pytest.raises(ValueError):
        builder.materialize(draft, instance.model_copy(update=change))
    assert not runtime.calls


@pytest.mark.parametrize(
    "field,value",
    [("repo", "different"), ("sha", "d" * 40), ("base_commit", "d" * 40), ("subject", "invented")],
)
def test_changed_seed_record_refused(grounded, field, value):
    builder, runtime, _, draft, instance = grounded
    changed = draft.model_copy(update={"seed": draft.seed.model_copy(update={field: value})})
    with pytest.raises(ValueError, match="harvest"):
        builder.materialize(changed, instance)
    assert not runtime.calls


def test_harvest_uniqueness_is_scoped_to_immutable_task_base(grounded, tmp_path):
    seed = grounded[2].mined_seed
    second = seed.model_copy(update={"base_commit": "d" * 40})
    path = tmp_path / "seeds.jsonl"
    path.write_text(seed.model_dump_json() + "\n" + second.model_dump_json() + "\n")
    store = SeedStore.from_jsonl(path)
    assert store.matching(seed.instance_id, seed.base_commit) == (seed,)
    assert store.matching(seed.instance_id, second.base_commit) == (second,)
    with pytest.raises(ValueError, match="duplicate"):
        SeedStore(records=(seed, seed), digest="fixture")


def test_original_namespace_and_third_program_stay_bound():
    names = {symbol.__name__ for symbol in PROGRAM_NAMESPACE}
    assert {
        "Generator",
        "Verifier",
        "Instance",
        "Provenance",
        "Cell",
        "Verdict",
        "Trajectory",
        "random",
        "Perturbation",
        "Channel",
    } <= names
    bound = ProgramSource(
        kind=ProgramKind.VERIFIER,
        entrypoint="V",
        source=(
            "class V(Verifier):\n"
            "    bound = (Generator, Verifier, Instance, Provenance, Cell, Verdict, Trajectory, "
            "random, Perturbation, Channel)\n"
            "    def verify(self, trajectory, oracle):\n"
            "        return Verdict(passed=True)\n"
        ),
    ).load()
    assert set(bound.bound) == set(PROGRAM_NAMESPACE)
    assert program("return result").load().__name__ == "P"
    with pytest.raises(ProgramError, match="must subclass"):
        program("return result").model_copy(update={"kind": ProgramKind.GENERATOR}).load()
    with pytest.raises(ValueError):
        Provenance(generator="G", generator_version="1", seed=0, factor_space="retired")


def test_opaque_inputs_reject_replacement_and_do_not_alias_parent(grounded, monkeypatch):
    _, _, _, draft, original = grounded
    executor = ConfinedPrograms()
    config = {"spec": original.spec, "oracle": original.oracle}
    captured = []

    def fake_worker(source, **request):
        captured.append(deepcopy(request))
        instance = original.model_copy(
            update={"spec": request["config"]["spec"], "oracle": request["config"]["oracle"]}
        )
        return {"instances": [instance.model_dump(mode="json")]}

    monkeypatch.setattr(executor, "_call", fake_worker)
    result = executor.generate(draft.generator, original.cell, 1, config, 1)[0]
    assert captured[0]["config"] == {
        "spec": {"__bound_input__": "spec"},
        "oracle": {"__bound_input__": "oracle"},
    }
    result.spec["pin"]["commit"] = "modified"
    assert config["spec"]["pin"]["commit"] == "a" * 40

    def replacing_worker(source, **request):
        return {"instances": [original.model_dump(mode="json")]}

    monkeypatch.setattr(executor, "_call", replacing_worker)
    with pytest.raises(ValueError, match="opaque"):
        executor.generate(draft.generator, original.cell, 1, config, 1)
