"""One episode through a local forwarded Devstral replica; never a vendor endpoint."""

import json
import math
import os
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from adversary.core.model import CompletionRequest, ModelInfo
from adversary.execution.backends.openai_compatible import ServedModel
from domains.swe_agents.environment.prun_integrity import strict_json
from domains.swe_agents.scripts.episode_bridge import (
    BridgeError,
    _encode,
    _lines,
    _request,
    _send,
    _write,
)
from domains.swe_agents.scripts.episode_budget import EpisodeBudget

CANONICAL_MODEL = "mistralai/Devstral-Small-2-24B-Instruct-2512"
MODEL_REVISION = "55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128"
LOCAL_REQUEST_LIMIT = 2_000_000
CONTEXT_LIMIT = 16384


def tokenize_request(
    base_url: str, model_id: str, request: CompletionRequest, timeout_seconds: float = 30
) -> int:
    """Use the deployed tokenizer and exactly the chat transport's message/tool encoding."""
    payload = {
        "model": model_id,
        "messages": [ServedModel._encode(m) for m in request.messages],
        "add_generation_prompt": True,
        "add_special_tokens": False,
    }
    if request.tools:
        payload["tools"] = list(request.tools)
    http_request = urllib.request.Request(
        base_url.rstrip("/").removesuffix("/v1") + "/tokenize",
        data=_encode(payload),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
        result = json.load(response)
    if (
        type(result.get("count")) is not int
        or result["count"] < 0
        or result.get("max_model_len") != CONTEXT_LIMIT
    ):
        raise BridgeError("tokenizer did not attest the registered context limit")
    return result["count"]


def fit_context(
    request: CompletionRequest, base_url: str, model_id: str, *, deadline: float | None = None
) -> tuple[CompletionRequest, dict[str, Any]]:
    """Evict oldest complete turns only, preserving initial instructions and latest turn."""
    messages = request.messages
    prefix = next((i for i, m in enumerate(messages) if m.role == "assistant"), len(messages))
    if any(m.role not in {"system", "user"} for m in messages[:prefix]):
        raise BridgeError("invalid initial transcript roles")
    groups = []
    index = prefix
    while index < len(messages):
        start = index
        assistant = messages[index]
        if assistant.role != "assistant":
            raise BridgeError("context projection requires complete assistant/tool turns")
        index += 1
        tool_ids = []
        while index < len(messages) and messages[index].role == "tool":
            tool_ids.append(messages[index].tool_call_id)
            index += 1
        expected = [call.id for call in assistant.tool_calls]
        if len(set(expected)) != len(expected) or sorted(tool_ids) != sorted(expected):
            raise BridgeError("incomplete or duplicate tool-result group")
        groups.append((start, index))
    trials = []
    cache = {}

    def measure(drop: int) -> tuple[CompletionRequest, int]:
        if drop not in cache:
            first = groups[drop][0] if groups else prefix
            effective = request.model_copy(
                update={"messages": messages[:prefix] + messages[first:]}
            )
            timeout = 30.0 if deadline is None else min(30.0, deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("interaction budget exhausted during context projection")
            count = tokenize_request(base_url, model_id, effective, timeout_seconds=timeout)
            trials.append({"dropped_groups": drop, "prompt_tokens": count})
            cache[drop] = (effective, count)
        return cache[drop]

    effective, count = measure(0)
    dropped = 0
    if count + request.max_tokens > CONTEXT_LIMIT:
        maximum = len(groups) - 1
        if maximum <= 0 or measure(maximum)[1] + request.max_tokens > CONTEXT_LIMIT:
            raise BridgeError("initial instructions and latest complete turn exceed token context")
        low, high = 1, maximum
        while low < high:
            middle = (low + high) // 2
            if measure(middle)[1] + request.max_tokens <= CONTEXT_LIMIT:
                high = middle
            else:
                low = middle + 1
        dropped = low
        effective, count = measure(dropped)
    removed = [i for start, stop in groups[:dropped] for i in range(start, stop)]
    return effective, {
        "kind": "exact_tokenized_recent_complete_turns_v1",
        "context_limit": CONTEXT_LIMIT,
        "reserved_output_tokens": request.max_tokens,
        "prompt_tokens": count,
        "removed_message_indices": removed,
        "dropped_groups": dropped,
        "original_message_count": len(messages),
        "effective_message_count": len(effective.messages),
        "tokenization_trials": trials,
    }


class DevstralModel(ServedModel):
    """Separate the serving alias from caller-attested checkpoint metadata."""

    @property
    def info(self) -> ModelInfo:
        return super().info.model_copy(update={"id": CANONICAL_MODEL, "version": MODEL_REVISION})


def run_local_bridge(
    argv: list[str],
    out: Path,
    base_url: str,
    model_id: str,
    expected_pin: dict[str, Any] | None = None,
    maxcalls: int | None = None,
    budget: EpisodeBudget | None = None,
) -> dict[str, Any]:
    """Persist bounded requests/results using one trusted controller and local replica.

    Pins supplied here are caller-attested deployment metadata, not an endpoint
    identity proof. The caller checks the serving revision before invoking this
    function. Byte limits do not prove that a request fits a tokenizer context.
    """
    if not re.fullmatch(r"http://127\.0\.0\.1:281(?:0[0-9]|10)/v1/?", base_url):
        raise ValueError("only registered loopback Devstral forwards are allowed")
    if model_id != "devstral-base-rate":
        raise ValueError("unexpected Devstral serving alias")
    budget = budget or EpisodeBudget(max_steps=100 if maxcalls is None else maxcalls)
    if maxcalls is not None and maxcalls != budget.max_steps:
        raise ValueError("maxcalls differs from shared budget")
    maxcalls = budget.max_steps
    if (
        not isinstance(argv, list)
        or not argv
        or any(type(a) is not str or "\x00" in a for a in argv)
    ):
        raise ValueError("trusted controller argv required")
    if expected_pin is not None and type(expected_pin) is not dict:
        raise ValueError("deployment pin must be a mapping")
    pin = {"model": CANONICAL_MODEL, "revision": MODEL_REVISION, **(expected_pin or {})}
    if pin["model"] != CANONICAL_MODEL or pin["revision"] != MODEL_REVISION:
        raise ValueError("deployment pin differs from frozen Devstral checkpoint")
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and any(key in arg for arg in argv):
        raise BridgeError("credentials must not appear in controller argv")
    metadata = {
        "source_kind": "devstral",
        "base_url": base_url,
        "model_id": model_id,
        "expected_pin": pin,
        "pin_evidence": "caller_attested",
        "maxcalls": maxcalls,
        "max_output_tokens_per_call": budget.max_output_tokens,
        "budget": budget.model_dump(),
        "max_request_bytes": LOCAL_REQUEST_LIMIT,
        "max_message_bytes": 65536,
        "context_limit": CONTEXT_LIMIT,
        "context_policy": "exact tokenizer; oldest complete turn eviction",
        "total_token_bound": None,
    }
    if key and key in _encode(metadata).decode():
        raise BridgeError("credential-like metadata refused")
    out = Path(out)
    out.mkdir(mode=0o700, exist_ok=False)
    _write(out / "registration.json", metadata)
    model = DevstralModel(
        base_url=base_url,
        model=model_id,
        api_key_env=None,
        version=MODEL_REVISION,
        timeout_seconds=120,
    )
    episodes: dict[str, tuple[int, int]] = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    attempts, process, stage = 0, None, "controller_start"
    attempted, known = False, False
    budget_exhausted = usage_unknown = False
    stop_reason = None
    try:
        env = {
            name: os.environ[name]
            for name in (
                "PATH",
                "HOME",
                "USER",
                "LOGNAME",
                "LANG",
                "SSH_AUTH_SOCK",
            )
            if name in os.environ
        }
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        for number, text in enumerate(_lines(process.stdout), 1):
            stage, attempted, known = "controller_event", False, False
            event = strict_json(text)
            if type(event) is not dict or type(event.get("event")) is not str:
                raise BridgeError("invalid controller event")
            if key and key in _encode(event).decode():
                raise BridgeError("credential-like event refused")
            if event["event"] != "model_request":
                if event["event"] == "episode_complete":
                    stop_reason = event.get("summary", {}).get("stop_reason")
                    budget_exhausted |= stop_reason in {"step_budget", "time_budget"}
                _write(out / f"event-{number:06d}.json", event)
                continue
            stage = "request_validation"
            if set(event) != {
                "event",
                "request",
                "episode_id",
                "call",
                "budget",
                "remaining_seconds",
            }:
                raise BridgeError("local request lacks explicit shared budget")
            if EpisodeBudget.model_validate(event["budget"]) != budget:
                raise BridgeError("controller and bridge budgets differ")
            remaining = event["remaining_seconds"]
            if (
                type(remaining) not in (int, float)
                or not math.isfinite(remaining)
                or not 0 < remaining <= budget.max_seconds
            ):
                raise BridgeError("invalid remaining interaction budget")
            call_deadline = time.monotonic() + remaining
            if budget_exhausted:
                raise BridgeError("model requested after budget exhaustion")
            if attempts >= maxcalls:
                raise BridgeError("episode call cap reached")
            request = _request(
                {k: v for k, v in event.items() if k not in {"budget", "remaining_seconds"}},
                episodes,
                1,
                call_limit=maxcalls,
                output_limit=budget.output_request_cap,
                request_byte_limit=LOCAL_REQUEST_LIMIT,
            )
            if any(
                len(m.content.encode("utf-8")) > 65536 or m.response_items for m in request.messages
            ):
                raise BridgeError("local transcript message exceeds supported bounds")
            if request.max_tokens > budget.max_output_tokens:
                raise BridgeError("request exceeds shared per-call output cap")
            request = request.model_copy(update={"reasoning_effort": None})
            stem = f"call-{attempts + 1:04d}"
            _write(out / f"{stem}-original-request.json", event)
            stage = "context_projection"
            try:
                request, context = fit_context(request, base_url, model_id, deadline=call_deadline)
            except TimeoutError:
                if time.monotonic() < call_deadline:
                    raise
                budget_exhausted = True
                _write(
                    out / f"{stem}-budget-stop.json",
                    {"stop_reason": "time_budget", "model_attempted": False},
                )
                _send(process.stdin, {"error": "interaction_budget_exhausted"})
                continue
            _write(out / f"{stem}-context.json", context)
            _write(
                out / f"{stem}-request.json",
                {
                    **event,
                    "request": request.model_dump(mode="json"),
                    "source_kind": "devstral",
                },
            )
            remaining = call_deadline - time.monotonic()
            if remaining <= 0:
                budget_exhausted = True
                _write(
                    out / f"{stem}-budget-stop.json",
                    {"stop_reason": "time_budget", "model_attempted": False},
                )
                _send(process.stdin, {"error": "interaction_budget_exhausted"})
                continue
            model.config = model.config.model_copy(
                update={"timeout_seconds": min(120.0, remaining)}
            )
            stage, attempted = "model_call", True
            attempts += 1
            try:
                result = model.complete(request)
            except Exception:
                if time.monotonic() < call_deadline:
                    raise
                budget_exhausted = usage_unknown = True
                _write(
                    out / f"{stem}-failure.json",
                    {"stop_reason": "time_budget", "usage_unknown": True, "retry_attempted": False},
                )
                _send(process.stdin, {"error": "interaction_budget_exhausted"})
                continue
            raw_usage = result.raw.get("usage")
            if not isinstance(raw_usage, dict) or any(
                type(raw_usage.get(name)) is not int or raw_usage[name] < 0
                for name in ("prompt_tokens", "completion_tokens")
            ):
                raise BridgeError("local response lacks measured token usage")
            known = True
            usage["input_tokens"] += raw_usage["prompt_tokens"]
            usage["output_tokens"] += raw_usage["completion_tokens"]
            completion = result.model_dump(mode="json")
            if key and key in _encode(completion).decode():
                raise BridgeError("credential-like response refused")
            _write(out / f"{stem}-completion.json", completion)
            stage = "completion_forward"
            _send(process.stdin, completion)
        stage = "controller_exit"
        process.stdin.close()
        if process.wait(timeout=10):
            raise BridgeError("controller exited unsuccessfully")
        summary = {
            "status": "complete",
            "source_kind": "devstral",
            "model_calls": attempts,
            "episodes": len(episodes),
            "usage": usage,
            "total_token_bound": None,
            "budget": budget.model_dump(),
            "budget_exhausted": budget_exhausted,
            "stop_reason": stop_reason,
            "usage_unknown": usage_unknown,
        }
        _write(out / "summary.json", summary)
        return summary
    except BaseException:
        _write(
            out / "failure.json",
            {
                "status": "failed",
                "stage": stage,
                "model_calls": attempts,
                "measured_usage": usage,
                "usage_unknown": usage_unknown or (attempted and not known),
                "retry_attempted": False,
            },
        )
        raise BridgeError(f"local episode bridge failed at {stage}; no retry attempted") from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            for stream in (process.stdin, process.stdout):
                stream.close()
