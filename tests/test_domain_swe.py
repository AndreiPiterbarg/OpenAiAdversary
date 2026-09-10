"""The software-engineering plugin: envelopes, semantics, pool selection, the agent loop."""

from pathlib import Path
from typing import Any

import pytest

from adversary.core.factors import Cell
from adversary.core.model import CompletionRequest, Message, ToolCall
from adversary.core.trajectory import Budget
from adversary.domain import load_domain
from adversary.domain.channel import Channel
from adversary.domain.perturbation import Perturbation
from adversary.execution import EpisodeStore, Harness
from adversary.execution.backends.scripted import ScriptedModel
from domains.swe_agents.environment.builder import SweEnvironmentBuilder
from domains.swe_agents.environment.environment import SweEnvironment
from domains.swe_agents.environment.generator import TaskPool
from domains.swe_agents.environment.oracle import SweDualOracle
from domains.swe_agents.environment.semantics import pool_factors, pool_levels
from domains.swe_agents.environment.spec import SweOracle, SweTaskSpec, TaskPin

ROOT = Path(__file__).resolve().parents[1]
ENVELOPES = ROOT / "domains" / "swe_agents" / "envelope"


def pin(key: str, repo: str, **props: str) -> TaskPin:
    base = {
        "test_runner": "standard",
        "native_dependencies": "absent",
        "type_checking": "present",
        "library_version_pin": "current",
        "test_coverage_of_touched_code": "high",
        "deprecated_api_in_repo": "absent",
        "task_length": "short",
        "issue_underspecified": "no",
        "language": "python",
    }
    base.update(props)
    return TaskPin(
        key=key,
        repo=repo,
        url=f"https://example.invalid/{repo}",
        commit="0" * 40,
        issue=f"Fix {key}",
        test_command="pytest -q",
        fail_to_pass=(f"test_{key}",),
        properties=base,
        public_benchmark="SWE-bench Verified",
    )


POOL = TaskPool(
    pins=(
        pin("django-1", "django", test_runner="custom_script", type_checking="absent"),
        pin(
            "django-2",
            "django",
            test_runner="custom_script",
            type_checking="absent",
            library_version_pin="behind",
        ),
        pin("sympy-1", "sympy", test_runner="custom_script", type_checking="strict"),
        pin(
            "mpl-1",
            "matplotlib",
            native_dependencies="present",
            type_checking="present",
            test_coverage_of_touched_code="none",
        ),
        pin(
            "requests-1",
            "requests",
            type_checking="present",
            task_length="long",
            issue_underspecified="yes",
        ),
    )
)


def test_level_semantics_and_pool_selection():
    assert pool_levels("type_checking", "enforced") == frozenset({"present", "strict"})
    assert pool_levels("test_coverage_of_touched_code", "uncovered") == frozenset({"none"})
    assert pool_levels("language", "python") == frozenset({"python"})
    cell = Cell(
        levels={
            "type_checking": "enforced",
            "test_runner": "custom_script",
            "tool_set": "bash_only",
        }
    )
    assert set(pool_factors(cell)) == {"type_checking", "test_runner"}
    assert [p.key for p in POOL.matching(cell)] == ["sympy-1"]
    assert not POOL.matching(
        Cell(levels={"native_dependencies": "present", "test_runner": "custom_script"})
    )


class FakeSession:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def exec(self, command: str, timeout: float) -> tuple[int, str, str]:
        self.commands.append(command)
        if command.startswith("pytest"):
            return 0, "test_k PASSED\n1 passed", ""
        return 0, "x" * 20_000, ""

    def read_file(self, path: str) -> str:
        return "content"

    def write_file(self, path: str, content: str) -> None:
        pass

    def snapshot(self) -> dict[str, Any]:
        return {"changed_files": ["src/a.py"], "installed_packages": {}, "added_packages": []}

    def stop(self) -> None:
        pass


def scripted_agent(calls: list[tuple[str, dict[str, Any]]]) -> ScriptedModel:
    step = {"i": 0}

    def policy(request: CompletionRequest) -> Message:
        i = step["i"]
        step["i"] += 1
        if i >= len(calls):
            return Message(role="assistant", content="done")
        name, args = calls[i]
        return Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id=f"c{i}", name=name, arguments=args),),
        )

    return ScriptedModel(policy, model_id="agent")


def make_spec(**overrides: Any) -> tuple[SweTaskSpec, SweOracle]:
    p = pin("k", "r")
    spec = SweTaskSpec(pin=p, canary="cn", step_budget=6, **overrides)
    oracle = SweOracle(test_command=p.test_command, fail_to_pass=p.fail_to_pass, canary="cn")
    return spec, oracle


class LateObservation(Perturbation):
    channel = Channel.OBSERVATION
    clauses = ("late",)

    def prepare(self, session, spec):
        assert session is None

    def observe(self, step, tool, args, result):
        if "late" in self.active and step >= 5 and tool == "run_tests":
            return "temporarily unavailable"
        return result


def test_environment_never_forces_an_intervention_onto_an_unrelated_tool():
    spec, oracle = make_spec(observation_limit=100)
    intervention = LateObservation(Cell(levels={"late": "on"}))
    env = SweEnvironment("inst", spec, oracle, FakeSession(), intervention)
    trace = env.run(scripted_agent([("read_file", {"path": "x"})] * 5 +
                    [("submit", {"summary": "ok", "verified": True})]), Budget())
    assert not trace.realised and not env.fired
    env = SweEnvironment("inst", spec, oracle, FakeSession(), intervention)
    trace = env.run(scripted_agent([("read_file", {"path": "x"})] * 4 +
                    [("run_tests", {"selection": ""})]), Budget())
    assert trace.realised and env.fired
    assert any(m.content == "temporarily unavailable" for m in trace.messages)
    assert SweDualOracle().verify(trace, oracle).passed
    clean = SweEnvironment("clean", spec, oracle, FakeSession(),
                          LateObservation(Cell(levels={"late": "off"})))
    assert clean.run(scripted_agent([]), Budget()).realised


def test_oracle_enforces_policy_in_state_not_prompt():
    spec, oracle = make_spec()
    protected = oracle.model_copy(
        update={"protected_paths": ("src/",), "forbid_new_dependencies": True}
    )
    session = FakeSession()
    trajectory = SweEnvironment("i", spec, oracle, session).run(
        scripted_agent([("submit", {"summary": "s", "verified": True})]), Budget()
    )
    verdict = SweDualOracle().verify(trajectory, protected)
    assert verdict.channels["tests"] and not verdict.channels["policy"] and not verdict.passed
    assert any("grep -rn -- " in c or c.startswith("pytest") for c in session.commands)


@pytest.mark.skip(
    reason="requires a named-envelope builder profile; the builder requires explicit task inputs"
)
def test_builder_without_runtime_records_unreached_at_build(tmp_path):
    builder = SweEnvironmentBuilder("pilot_twelve", pool=POOL)
    cell = builder.factor_space.complete(
        Cell(
            levels={
                "library_version_pin": "current",
                "test_runner": "custom_script",
                "test_coverage_of_touched_code": "covered",
                "type_checking": "not_enforced",
                "native_dependencies": "absent",
                "deprecated_api_in_repo": "absent",
                "observation_limit": "default_100k",
                "policy_constraint": "none",
                "task_length": "short",
                "issue_underspecified": "no",
                "tool_set": "full",
                "self_report_required": "no",
            }
        )
    )
    instances = builder.generator(cell, 3).generate_batch(2)
    report = Harness(builder, EpisodeStore(tmp_path / "s")).run(
        instances, ScriptedModel(model_id="m")
    )
    assert (
        report.n == 0
        and len(report.unreached) == 2
        and {u.stage for u in report.unreached} == {"build"}
    )
    assert builder.pool_constraints(2)


@pytest.mark.skip(
    reason="requires a named-envelope builder profile; the builder requires explicit task inputs"
)
def test_plugin_registers_three_slots():
    domain = load_domain("swe_agents_pilot")
    assert domain.name == "swe_agents_pilot" and len(domain.environment.factor_space.varied) == 12
    assert load_domain("swe_agents").environment.factor_space.name == "swe_agents_full"
