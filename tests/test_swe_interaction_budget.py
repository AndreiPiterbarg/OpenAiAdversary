"""Real loop boundaries, independent of model transport and final verifier duration."""

import pytest

from adversary.core.model import Message, ToolCall
from adversary.core.trajectory import Budget
from adversary.execution.backends.scripted import ScriptedModel
from domains.swe_agents.environment import environment as module
from tests.test_domain_swe import FakeSession, make_spec, scripted_agent


class Final:
    def __init__(self, clock=None):
        self.calls = 0
        self.clock = clock

    def evaluate(self, session):
        self.calls += 1
        if self.clock is not None:
            self.clock[0] += 20
        return {"test_results": {"exit": 0}}


def build(session=None, final=None):
    spec, oracle = make_spec()
    spec = spec.model_copy(update={"step_budget": 100, "tool_set": "bash_only"})
    return module.SweEnvironment(
        "i", spec, oracle, session or FakeSession(), final_oracle=final or Final()
    )


def test_continues_beyond_fifty_and_records_submit():
    trace = build().run(
        scripted_agent([("shell", {"command": "true"})] * 60 + [("submit", {"verified": False})]),
        Budget(max_steps=100, max_seconds=600),
    )
    assert trace.steps == 61
    assert trace.stop_reason == "submitted" and not trace.truncated
    assert trace.final_state["interaction_outcome"]["max_steps"] == 100


def test_step_cap_is_explicit_even_when_final_tests_pass():
    trace = build().run(scripted_agent([("shell", {"command": "true"})] * 3), Budget(max_steps=2))
    assert trace.steps == 2 and trace.truncated
    assert trace.stop_reason == "step_budget"
    assert trace.final_state["interaction_outcome"]["budget_exhausted"]


def test_tool_timeout_clamps_to_remaining_and_cancels_rest_of_group(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(module.time, "perf_counter", lambda: clock[0])
    timeouts = []

    class Session(FakeSession):
        def exec(self, command, timeout):
            timeouts.append(timeout)
            clock[0] += timeout
            return 0, "ok", ""

    def policy(_):
        return Message(
            role="assistant",
            tool_calls=(
                ToolCall(id="one", name="shell", arguments={"command": "slow"}),
                ToolCall(id="two", name="shell", arguments={"command": "must-not-run"}),
            ),
        )

    final = Final(clock)
    trace = build(Session(), final).run(ScriptedModel(policy), Budget(max_seconds=2))
    assert timeouts == [2]
    assert trace.stop_reason == "time_budget" and trace.truncated
    assert [m.tool_call_id for m in trace.messages if m.role == "tool"] == ["one", "two"]
    assert trace.final_state["interaction_outcome"]["interaction_seconds"] == 2
    assert final.calls == 1 and trace.usage.wall_seconds == 22


@pytest.mark.parametrize("elapsed,budget_expired", [(1, False), (3, True)])
def test_model_timeout_is_budget_stop_only_at_deadline(monkeypatch, elapsed, budget_expired):
    clock = [0.0]
    monkeypatch.setattr(module.time, "perf_counter", lambda: clock[0])

    def policy(_):
        clock[0] += elapsed
        raise TimeoutError("transport timed out")

    final = Final()
    env = build(final=final)
    if not budget_expired:
        with pytest.raises(TimeoutError):
            env.run(ScriptedModel(policy), Budget(max_seconds=2))
        assert final.calls == 0
    else:
        trace = env.run(ScriptedModel(policy), Budget(max_seconds=2))
        assert trace.stop_reason == "time_budget" and final.calls == 1
