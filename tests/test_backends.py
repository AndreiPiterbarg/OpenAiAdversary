from adversary.core.model import LicenseClass, Message, ToolCall
from adversary.execution.backends import MODELS, build_model
from adversary.execution.backends.frontier import anthropic_messages, anthropic_tools
from adversary.execution.backends.transformers_local import parse_tool_calls


def test_frontier_backends_are_restricted_regardless_of_config():
    for name, kwargs in (
        ("openai", {"model": "gpt-x"}),
        ("gemini", {"model": "g"}),
        ("anthropic", {"model": "c"}),
    ):
        model = build_model(
            name, **kwargs, **({"license": "permissive"} if name != "anthropic" else {})
        )
        assert model.info.license is LicenseClass.RESTRICTED and not model.shippable
    assert not build_model("served", base_url="http://x/v1", model="q").shippable
    assert build_model("served", base_url="http://x/v1", model="q", license="permissive").shippable
    assert "scripted" in MODELS and "transformers" in MODELS


def test_anthropic_message_and_tool_conversion():
    tools = (
        {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "run",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
            },
        },
    )
    converted = anthropic_tools(tools)
    assert converted == [
        {"name": "shell", "description": "run", "input_schema": tools[0]["function"]["parameters"]}
    ]
    messages = (
        Message(role="system", content="sys"),
        Message(role="user", content="fix it"),
        Message(
            role="assistant",
            content="",
            tool_calls=(
                ToolCall(id="c1", name="shell", arguments={"command": "ls"}),
                ToolCall(id="c2", name="shell", arguments={"command": "pwd"}),
            ),
        ),
        Message(role="tool", content="a", tool_call_id="c1"),
        Message(role="tool", content="b", tool_call_id="c2"),
        Message(role="assistant", content="done"),
    )
    encoded = anthropic_messages(messages)
    assert [m["role"] for m in encoded] == ["user", "assistant", "user", "assistant"]
    assert [b["type"] for b in encoded[1]["content"]] == ["tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in encoded[2]["content"]] == ["c1", "c2"]
    assert encoded[3]["content"] == [{"type": "text", "text": "done"}]


def test_hermes_tool_call_parsing():
    text = (
        'Thinking.\n<tool_call>\n{"name": "shell", "arguments": {"command": "ls"}}\n</tool_call>\n'
        '<tool_call>{"name": "submit", "arguments": {"verified": true}}</tool_call>'
    )
    content, calls = parse_tool_calls(text)
    assert content == "Thinking." and [c.name for c in calls] == ["shell", "submit"]
    assert calls[1].arguments == {"verified": True} and calls[0].id != calls[1].id
    assert parse_tool_calls("plain answer") == ("plain answer", ())


def test_served_pinned_decoding_payload(monkeypatch):
    from adversary.core.model import CompletionRequest
    from adversary.execution.backends import openai_compatible as wire

    sent = []

    def post(url, payload, headers, timeout):
        sent.append((url, payload))
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(wire, "post_json", post)
    model = build_model("served", base_url="http://local/v1", model="q")
    model.complete(
        CompletionRequest(
            messages=(),
            temperature=1,
            top_p=0.95,
            top_k=20,
            chat_template_kwargs={"enable_thinking": False},
            seed=7,
        )
    )
    payload = sent[0][1]
    assert payload["temperature"] == 1 and payload["top_p"] == 0.95
    assert payload["top_k"] == 20 and payload["seed"] == 7
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_astra_responses_tool_roundtrip_and_effort(monkeypatch):
    import pytest

    from adversary.core.model import CompletionRequest
    from adversary.execution.backends import responses as wire

    sent = []
    native = [
        {"type": "reasoning", "id": "r", "encrypted_content": "opaque", "summary": []},
        {
            "type": "function_call",
            "call_id": "c",
            "name": "shell",
            "arguments": '{"command":"pwd"}',
        },
    ]

    def post(url, payload, headers, timeout):
        sent.append((url, payload))
        return {
            "status": "completed",
            "reasoning": {"effort": "low"},
            "output": native,
            "usage": {"input_tokens": 12, "output_tokens": 9},
        }

    monkeypatch.setattr(wire, "post_json", post)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    model = build_model("openai", model="gpt-6-astra")
    request = CompletionRequest(messages=(Message(role="user", content="fix"),))
    reply = model.complete(request)
    assert reply.message.tool_calls[0].arguments == {"command": "pwd"}
    assert reply.usage.output_tokens == 9
    model.complete(
        request.model_copy(
            update={
                "messages": (
                    *request.messages,
                    reply.message,
                    Message(role="tool", tool_call_id="c", content="/project"),
                )
            }
        )
    )
    assert sent[1][0].endswith("/responses")
    payload = sent[1][1]
    assert payload["input"][1:3] == native
    assert payload["input"][-1]["call_id"] == "c"
    assert payload["reasoning"] == {"effort": "low"}
    assert "temperature" not in payload and "max_tokens" not in payload
    assert payload["max_output_tokens"] == request.max_tokens
    with pytest.raises(ValueError, match="effort"):
        model.complete(request.model_copy(update={"reasoning_effort": "high"}))
    before = len(sent)
    with pytest.raises(ValueError, match="sampling"):
        model.complete(request.model_copy(update={"top_p": 0.95}))
    assert len(sent) == before


def test_local_backend_honors_sampling_and_restores_rng():
    import torch

    from adversary.core.model import CompletionRequest
    from adversary.execution.backends.transformers_local import TransformersModel

    class Tokenizer:
        pad_token_id = 0
        eos_token_id = 1

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            return {"input_ids": torch.tensor([[1, 2]])}

        def decode(self, output, **kwargs):
            return "ok"

    class Weights:
        device = torch.device("cpu")

        def generate(self, input_ids, **kwargs):
            assert kwargs["temperature"] == 1
            assert kwargs["top_p"] == 0.95 and kwargs["top_k"] == 20
            assert torch.initial_seed() == 123
            torch.rand(4)
            return torch.tensor([[1, 2, 3]])

    model = TransformersModel(model_id="unused")
    model._model, model._tokenizer = Weights(), Tokenizer()
    state = torch.random.get_rng_state()
    reply = model.complete(
        CompletionRequest(
            messages=(),
            temperature=1,
            top_p=0.95,
            top_k=20,
            seed=123,
            chat_template_kwargs={"enable_thinking": False},
        )
    )
    assert reply.message.content == "ok" and reply.usage.output_tokens == 1
    assert torch.equal(state, torch.random.get_rng_state())
