"""Episode dispatch and visible intervention evidence, without API calls."""

import pytest

from adversary.core.factors import Cell
from adversary.core.model import Message, ToolCall
from adversary.core.trajectory import Budget
from adversary.execution.backends.scripted import ScriptedModel
from domains.swe_agents.environment.environment import SweEnvironment
from tests.test_domain_swe import FakeSession, LateObservation, make_spec, scripted_agent


@pytest.mark.parametrize("name", ["install", "read_file", "unadvertised"])
def test_unadvertised_tool_refused_before_session_access(name):
    spec, oracle = make_spec(tool_set="bash_only")
    session = FakeSession()
    environment = SweEnvironment("guard", spec, oracle, session)
    with pytest.raises(ValueError, match="not advertised"):
        environment._dispatch(ToolCall(id="bad", name=name, arguments={}), 1)
    assert not session.commands


def test_submit_stops_later_calls_in_the_same_completion():
    spec, oracle = make_spec()
    session = FakeSession()
    model = ScriptedModel(lambda _: Message(role="assistant", tool_calls=(
        ToolCall(id="done", name="submit", arguments={"summary": "done", "verified": True}),
        ToolCall(id="later", name="shell", arguments={"command": "touch unwanted"}),
    )))
    trace = SweEnvironment("guard", spec, oracle, session).run(model, Budget())
    assert model.calls == 1
    assert not any("unwanted" in command for command in session.commands)
    assert [m.tool_call_id for m in trace.messages if m.role == "tool"] == ["done", "later"]
    assert "Not executed" in trace.messages[-1].content
    assert trace.stop_reason == "submitted"


@pytest.mark.parametrize("visible_change", [False, True])
def test_realization_requires_a_change_to_visible_clipped_observation(visible_change):
    class Session(FakeSession):
        def read_file(self, path):
            return "same prefix hidden suffix"

    class Observer(LateObservation):
        def observe(self, step, tool, args, result):
            if tool == "read_file":
                return ("DIFF prefix" if visible_change else "same prefix") + " replaced suffix"
            return result

    spec, oracle = make_spec(observation_limit=4)
    environment = SweEnvironment(
        "guard", spec, oracle, Session(), Observer(Cell(levels={"late": "on"})),
    )
    trace = environment.run(scripted_agent([
        ("read_file", {"path": "file"}),
        ("submit", {"summary": "done", "verified": True}),
    ]), Budget())
    assert trace.realised is visible_change
    assert bool(environment.fired) is visible_change
    delivered = next(m.content for m in trace.messages if m.role == "tool")
    assert delivered.startswith("DIFF" if visible_change else "same")


@pytest.mark.parametrize("cap", [256, 512, 4096])
def test_output_cap_is_sent_on_every_call(cap):
    observed = []

    def policy(request):
        observed.append(request.max_tokens)
        if len(observed) == 1:
            return Message(role="assistant", tool_calls=(
                ToolCall(id="read", name="read_file", arguments={"path": "file"}),
            ))
        return Message(role="assistant", content="done")

    spec, oracle = make_spec()
    SweEnvironment("guard", spec, oracle, FakeSession(), max_output_tokens=cap).run(
        ScriptedModel(policy), Budget(),
    )
    assert observed == [cap, cap]


@pytest.mark.parametrize("cap", [True, 0, -1, 1.5, None])
def test_invalid_output_cap_refused_at_construction(cap):
    spec, oracle = make_spec()
    with pytest.raises(ValueError, match="positive integer"):
        SweEnvironment("guard", spec, oracle, FakeSession(), max_output_tokens=cap)
