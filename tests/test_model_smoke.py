"""Wire-level smoke bounds with fake transport only; no live model requests."""

import pytest

from adversary.core.model import CompletionRequest, Message
from adversary.execution.backends import responses
from domains.swe_agents.scripts.model_smoke import (
    MAX_INPUT_BYTES,
    ModelSmokeError,
    model_smoke,
    render_restricted_candidate,
)


def request(**updates):
    return CompletionRequest(
        messages=(Message(role="user", content="Reply OK."),), max_tokens=256,
    ).model_copy(update=updates)


@pytest.fixture
def transport(monkeypatch):
    calls = []

    def send(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {
            "status": "completed", "reasoning": {"effort": "low"},
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "OK"},
            ]}],
            "usage": {"input_tokens": 9, "output_tokens": 4},
        }

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(responses, "post_json", send)
    return calls


@pytest.mark.parametrize("cap", [256, 512])
def test_one_request_low_effort_and_actual_usage(transport, cap, capsys):
    result = model_smoke(request(max_tokens=cap))
    assert len(transport) == 1
    url, payload, headers, timeout = transport[0]
    assert url == "https://api.openai.com/v1/responses"
    assert payload["model"] == "gpt-6-astra"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_output_tokens"] == cap and payload["store"] is False
    assert "tools" not in payload
    assert headers["Authorization"] == "Bearer synthetic-test-key"
    assert timeout == 120
    assert result.message.content == "OK"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (9, 4)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("changes", [
    {"max_tokens": 513}, {"max_tokens": True}, {"reasoning_effort": "high"},
    {"messages": ()}, {"tools": ({"type": "function"},)}, {"temperature": 0.1},
    {"seed": 1}, {"thinking_budget": 1},
    {"messages": (Message(role="user", content=" "),)},
    {"messages": (Message(role="assistant", content="OK"),)},
    {"messages": (Message(role="user", content="x", response_items=({"input": "x"},)),)},
    {"messages": (Message(role="user", content="x", tool_call_id="call"),)},
    {"messages": (Message(role="user", content="é" * (MAX_INPUT_BYTES // 2 + 1)),)},
    {"messages": (Message(role="user", content="\ud800"),)},
])
def test_unsupported_or_oversized_request_makes_no_call(transport, changes):
    with pytest.raises(ValueError):
        model_smoke(request(**changes))
    assert not transport


def test_missing_key_makes_no_call(transport, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ModelSmokeError, match="no request made"):
        model_smoke(request())
    assert not transport


def test_failure_is_not_retried_or_logged(transport, monkeypatch, capsys):
    def fail(*args):
        transport.append(args)
        raise RuntimeError("synthetic-test-key echoed by endpoint")

    monkeypatch.setattr(responses, "post_json", fail)
    with pytest.raises(ModelSmokeError) as error:
        model_smoke(request())
    assert len(transport) == 1
    assert "synthetic-test-key" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert capsys.readouterr() == ("", "")


def test_incomplete_response_is_returned_without_continuation(transport, monkeypatch):
    def incomplete(*args):
        transport.append(args)
        return {
            "status": "incomplete", "reasoning": {"effort": "low"}, "output": [],
            "usage": {"input_tokens": 9, "output_tokens": 256},
        }

    monkeypatch.setattr(responses, "post_json", incomplete)
    result = model_smoke(request())
    assert len(transport) == 1
    assert result.finish_reason == "length" and result.usage.output_tokens == 256


def test_missing_usage_cannot_be_reported_as_zero(transport, monkeypatch):
    def no_usage(*args):
        transport.append(args)
        return {"status": "completed", "reasoning": {"effort": "low"}, "output": []}

    monkeypatch.setattr(responses, "post_json", no_usage)
    with pytest.raises(ModelSmokeError, match="lacks measured token usage"):
        model_smoke(request())
    assert len(transport) == 1


@pytest.fixture
def pristine(monkeypatch):
    import hashlib

    from domains.swe_agents.environment import factory_verifier

    # Only this unit fixture replaces the pin; production admission keeps its hash.
    source = 'class Maybe:\n    def evaluate_pre(self):\n' + factory_verifier._REPAIR_LINE
    monkeypatch.setattr(factory_verifier, 'DECLARATIONS_SHA256', hashlib.sha256(source.encode()).hexdigest())
    return {'factory/declarations.py': source, 'factory/__init__.py': '# fixture\n'}


@pytest.mark.parametrize('method', ['evaluate', 'evaluate_pre'])
@pytest.mark.parametrize('keyword', ['extra', 'overrides'])
def test_rendered_choice_is_admitted_and_preserves_other_sources(pristine, method, keyword):
    import json

    original = dict(pristine)
    candidate, admission = render_restricted_candidate(
        json.dumps({'method': method, 'keyword': keyword}), pristine,
    )
    assert pristine == original
    assert candidate['factory/__init__.py'] == pristine['factory/__init__.py']
    assert f'self.decider.{method}(instance=instance, step=step, {keyword}={{}})' in candidate['factory/declarations.py']
    assert (admission['method'], admission['keyword']) == (method, keyword)
    assert admission['arbitrary_python_admitted'] is False


@pytest.mark.parametrize('text', [
    None, {}, b'{}', '[]', 'null', 'true', '{}',
    '{"method":"evaluate","keyword":"extra","code":"pass"}',
    '{"method":"evaluate","method":"evaluate_pre","keyword":"extra"}',
    '{"method":null,"keyword":"extra"}',
    '{"method":"evaluate","keyword":1}',
    '{"method":"evaluate()","keyword":"extra"}',
    '{"method":"evaluate","keyword":"kwargs"}',
    '```json\n{"method":"evaluate","keyword":"extra"}\n```',
    'import os', '{"method":"evaluate","keyword":"extra"} {}',
    '{"method":NaN,"keyword":"extra"}', '\ud800', ' ' * 513,
])
def test_invalid_output_never_becomes_candidate_sources(pristine, text):
    with pytest.raises(ValueError):
        render_restricted_candidate(text, pristine)


def test_rendering_requires_frozen_pristine_source(pristine):
    pristine['factory/declarations.py'] += '# tampered\n'
    with pytest.raises(ValueError, match='frozen source'):
        render_restricted_candidate('{"method":"evaluate_pre","keyword":"overrides"}', pristine)
