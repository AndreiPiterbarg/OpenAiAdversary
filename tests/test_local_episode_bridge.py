"""Loopback-only relay with fake transport and real local controller pipes."""

import json

import pytest

from adversary.execution.backends import openai_compatible
from domains.swe_agents.scripts import local_episode_bridge as local
from tests.test_episode_bridge import controller, event


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def post(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2},
        }

    monkeypatch.setattr(openai_compatible, "post_json", post)
    monkeypatch.setattr(local, "tokenize_request", lambda *args, **kwargs: 100)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return calls


def run(tmp_path, events, **kwargs):
    budget = kwargs.get("budget") or local.EpisodeBudget(max_steps=kwargs.get("maxcalls", 100))
    events = [
        {
            **e,
            "budget": e.get("budget", budget.model_dump()),
            "remaining_seconds": e.get("remaining_seconds", budget.max_seconds),
        }
        if e.get("event") == "model_request"
        else e
        for e in events
    ]
    return local.run_local_bridge(
        controller(events),
        tmp_path / "ledger",
        "http://127.0.0.1:28103/v1",
        "devstral-base-rate",
        **kwargs,
    )


def test_local_wire_usage_and_durable_completion(tmp_path, fake, monkeypatch):
    original = local._send

    def checked(stream, result):
        assert (
            json.loads(next((tmp_path / "ledger").glob("*completion.json")).read_text()) == result
        )
        return original(stream, result)

    monkeypatch.setattr(local, "_send", checked)
    summary = run(
        tmp_path, [event(reasoning_effort="low")], expected_pin={"revision": local.MODEL_REVISION}
    )
    assert summary["usage"] == {"input_tokens": 11, "output_tokens": 2}
    assert len(fake) == 1
    url, payload, headers, timeout = fake[0]
    assert url == "http://127.0.0.1:28103/v1/chat/completions"
    assert payload["model"] == "devstral-base-rate" and "reasoning_effort" not in payload
    assert not headers and timeout == 120
    metadata = json.loads((tmp_path / "ledger/registration.json").read_text())
    assert metadata["expected_pin"]["model"] == local.CANONICAL_MODEL


def test_different_checkpoint_refused_before_launch(tmp_path, fake):
    with pytest.raises(ValueError, match="checkpoint"):
        run(tmp_path, [], expected_pin={"revision": "a" * 40})
    assert not fake


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "http://localhost:28103/v1",
        "http://127.0.0.1:28111/v1",
        "http://127.0.0.1:28103/v1?elsewhere",
    ],
)
def test_nonregistered_endpoint_refused(tmp_path, fake, url):
    with pytest.raises(ValueError):
        local.run_local_bridge(controller([]), tmp_path / "ledger", url, "devstral-base-rate")
    assert not fake


@pytest.mark.parametrize(
    "events,kwargs,expected",
    [
        ([event(), event(call=2)], {"maxcalls": 1}, 1),
        ([event(), event(episode="other")], {}, 1),
        ([event(max_tokens=1025)], {}, 0),
        ([event(messages=[{"role": "user", "content": "x" * 65537}])], {}, 0),
    ],
)
def test_request_and_episode_limits(tmp_path, fake, events, kwargs, expected):
    with pytest.raises(local.BridgeError):
        run(tmp_path, events, **kwargs)
    assert len(fake) == expected


def test_transport_failure_no_retry_unknown_usage(tmp_path, fake, monkeypatch):
    def fail(*args):
        fake.append(args)
        raise RuntimeError("untrusted failure")

    monkeypatch.setattr(openai_compatible, "post_json", fail)
    with pytest.raises(local.BridgeError):
        run(tmp_path, [event()])
    assert len(fake) == 1
    failure = json.loads((tmp_path / "ledger/failure.json").read_text())
    assert failure["usage_unknown"] and not failure["retry_attempted"]


@pytest.mark.parametrize("port", [28101, 28102])
def test_newly_free_gpu_endpoints_registered(tmp_path, fake, port):
    result = local.run_local_bridge(
        controller(
            [{**event(), "budget": local.EpisodeBudget().model_dump(), "remaining_seconds": 600.0}]
        ),
        tmp_path / "ledger",
        f"http://127.0.0.1:{port}/v1",
        "devstral-base-rate",
    )
    assert result["model_calls"] == 1


def test_full_pool_ten_call_cap_is_separate_from_astra(tmp_path, fake):
    with pytest.raises(local.BridgeError):
        run(tmp_path, [event(call=i) for i in range(1, 12)], maxcalls=10)
    assert len(fake) == 10


def test_local_larger_transcript_bound_does_not_change_paid_bridge_default(tmp_path, fake):
    from domains.swe_agents.scripts.episode_bridge import BridgeError, _request

    messages = [{"role": "user", "content": "x" * 12000} for _ in range(3)]
    request_event = event(messages=messages)
    with pytest.raises(BridgeError, match="byte limit"):
        _request(request_event, {}, 1)
    result = run(tmp_path, [request_event])
    assert result["model_calls"] == 1
    metadata = json.loads((tmp_path / "ledger/registration.json").read_text())
    assert metadata["max_request_bytes"] == 2_000_000
    assert metadata["max_message_bytes"] == 65536


def test_local_transcript_still_bounded_before_model_call(tmp_path, fake):
    from domains.swe_agents.scripts.episode_bridge import BridgeError

    messages = [{"role": "user", "content": "x" * 12000} for _ in range(180)]
    with pytest.raises(BridgeError):
        run(tmp_path, [event(messages=messages)])
    assert not fake


def test_exact_context_projection_keeps_initial_and_complete_latest_turn(monkeypatch):
    from adversary.core.model import CompletionRequest, Message, ToolCall

    messages = [Message(role="system", content="system"), Message(role="user", content="issue")]
    for i in range(4):
        messages.extend(
            [
                Message(
                    role="assistant", tool_calls=(ToolCall(id=str(i), name="shell", arguments={}),)
                ),
                Message(role="tool", tool_call_id=str(i), content=str(i)),
            ]
        )
    request = CompletionRequest(messages=tuple(messages), max_tokens=1024)
    monkeypatch.setattr(
        local, "tokenize_request", lambda _u, _m, r, **kwargs: 1000 + 3000 * len(r.messages)
    )
    effective, audit = local.fit_context(request, "url", "model")
    assert effective.messages[:2] == tuple(messages[:2])
    assert effective.messages[2:] == tuple(messages[-2:])
    assert audit["removed_message_indices"] == list(range(2, 8))
    assert audit["prompt_tokens"] + audit["reserved_output_tokens"] <= 16384


def test_oversized_initial_context_never_silently_truncated(monkeypatch):
    from adversary.core.model import CompletionRequest, Message

    request = CompletionRequest(
        messages=(Message(role="user", content="original issue"),), max_tokens=1024
    )
    monkeypatch.setattr(local, "tokenize_request", lambda *a, **kwargs: 16000)
    with pytest.raises(local.BridgeError, match="initial instructions"):
        local.fit_context(request, "url", "model")


def test_incomplete_tool_group_cannot_be_evicted(monkeypatch):
    from adversary.core.model import CompletionRequest, Message, ToolCall

    request = CompletionRequest(
        messages=(
            Message(role="user", content="issue"),
            Message(
                role="assistant", tool_calls=(ToolCall(id="missing", name="shell", arguments={}),)
            ),
        ),
        max_tokens=1024,
    )
    with pytest.raises(local.BridgeError, match="incomplete"):
        local.fit_context(request, "url", "model")


def test_fifty_local_calls_allowed_without_paid_default_change(tmp_path, fake):
    result = run(tmp_path, [event(call=i) for i in range(1, 51)], maxcalls=50)
    assert result["model_calls"] == len(fake) == 50
    from domains.swe_agents.scripts.episode_bridge import _request

    with pytest.raises(local.BridgeError, match="call index"):
        _request(event(call=9), {"one": (8, 4096)}, 1)


def test_continues_beyond_fifty_under_shared_hundred_budget(tmp_path, fake):
    result = run(tmp_path, [event(call=i) for i in range(1, 62)])
    assert result["model_calls"] == len(fake) == 61
    assert result["budget"]["max_steps"] == 100


def test_mismatched_budget_refused_before_model(tmp_path, fake):
    with pytest.raises(local.BridgeError):
        run(tmp_path, [{**event(), "budget": local.EpisodeBudget(max_steps=50).model_dump()}])
    assert not fake


def test_remaining_time_bounds_model_http_timeout(tmp_path, fake):
    run(tmp_path, [{**event(), "remaining_seconds": 0.5}])
    assert 0 < fake[0][3] <= 0.5


def test_exhausted_model_timeout_is_durable_and_forwarded(tmp_path, fake, monkeypatch):
    import time

    def expire(url, payload, headers, timeout):
        time.sleep(timeout + 0.01)
        raise TimeoutError("expired")

    monkeypatch.setattr(openai_compatible, "post_json", expire)
    import sys

    payload = {**event(), "remaining_seconds": 0.02, "budget": local.EpisodeBudget().model_dump()}
    source = (
        "import json,sys\nprint(" + repr(json.dumps(payload)) + ",flush=True)\n"
        "assert json.loads(sys.stdin.readline()) == {'error':'interaction_budget_exhausted'}\n"
        "print(json.dumps({'event':'finished'}),flush=True)\n"
    )
    result = local.run_local_bridge(
        [sys.executable, "-c", source],
        tmp_path / "ledger",
        "http://127.0.0.1:28103/v1",
        "devstral-base-rate",
    )
    assert result["budget_exhausted"] and result["usage_unknown"]
    failure = json.loads((tmp_path / "ledger/call-0001-failure.json").read_text())
    assert failure["usage_unknown"] and not failure["retry_attempted"]


def test_context_timeout_stops_without_model_attempt(tmp_path, fake, monkeypatch):
    import sys
    import time

    def expire(*args, timeout_seconds, **kwargs):
        assert 0 < timeout_seconds <= 0.02
        time.sleep(timeout_seconds + 0.01)
        raise TimeoutError("tokenizer deadline")

    monkeypatch.setattr(local, "tokenize_request", expire)
    payload = {**event(), "remaining_seconds": 0.02, "budget": local.EpisodeBudget().model_dump()}
    source = (
        "import json,sys\nprint(" + repr(json.dumps(payload)) + ",flush=True)\n"
        "assert json.loads(sys.stdin.readline()) == {'error':'interaction_budget_exhausted'}\n"
    )
    result = local.run_local_bridge(
        [sys.executable, "-c", source],
        tmp_path / "ledger",
        "http://127.0.0.1:28103/v1",
        "devstral-base-rate",
    )
    assert result["budget_exhausted"] and not result["usage_unknown"]
    assert result["model_calls"] == 0 and not fake
