import io
import json

import pytest

from adversary.core.model import Completion, CompletionRequest, Message, Usage
from domains.swe_agents.scripts.interactive_adversary import summarize
from domains.swe_agents.scripts.interactive_astra import AstraRelay, registration
from tests.test_tier1_grounding import grounded  # noqa: F401


def test_four_single_cells_never_five_execution_claim(grounded):  # noqa: F811
    draft = grounded[3].model_copy(update={"clauses": ("a", "b")})
    value = registration(draft, {"key": "factory"})
    assert len(value["runs"]) == 4
    assert [tuple(x["cell"].values()) for x in value["runs"]] == [
        ("off", "off"),
        ("on", "off"),
        ("off", "on"),
        ("on", "on"),
    ]
    result = summarize([{**x, "diagnostic_passed": True} for x in value["runs"]])
    assert all(x["task_failure"] is None for x in result["groups"])
    assert value["api_sampling"]["seed"] is None


def test_relay_records_requests_and_measured_usage(tmp_path, monkeypatch):
    import sys

    result = Completion(
        message=Message(role="assistant", content="done"),
        usage=Usage(input_tokens=5, output_tokens=2),
    )
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO((result.model_dump_json() + "\n").encode()))
    )
    model = AstraRelay("one", tmp_path)
    model.complete(
        CompletionRequest(messages=(Message(role="user", content="issue"),), max_tokens=1024)
    )
    assert model.completed_calls == model.calls == 1
    assert model.usage.input_tokens == 5
    assert json.loads((tmp_path / "request-1.json").read_text())["reasoning_effort"] == "low"
    model.calls = 20
    with pytest.raises(ValueError):
        model.complete(CompletionRequest(messages=(), max_tokens=1024))
