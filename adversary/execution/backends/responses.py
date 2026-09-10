"""Stateless Responses transport for tool-using reasoning targets.

The transcript carries returned items, including encrypted reasoning, so separate episodes
never share backend state. The wire contract is the official Astra guide and Responses API.
"""

import time
from typing import Any

from adversary.core.model import Completion, CompletionRequest, Message, ToolCall, Usage
from adversary.execution.backends.openai_compatible import ServedModel, _dump_args, _parse_args
from adversary.execution.http import post_json


def encode_input(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
    """Replay native assistant items; encode ordinary turns and tool results."""
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "assistant" and message.response_items:
            items.extend(message.response_items)
        elif message.role == "tool":
            if not message.tool_call_id:
                raise ValueError("tool result has no call id")
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
        else:
            if message.content:
                items.append({"role": message.role, "content": message.content})
            items.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": _dump_args(call.arguments),
                }
                for call in message.tool_calls
            )
    return items


def complete_responses(model: ServedModel, request: CompletionRequest) -> Completion:
    """Send Astra's supported parameters and require the effort echo to match."""
    if (
        request.thinking_budget is not None
        or request.temperature != 0
        or any(
            getattr(request, key) is not None
            for key in ("top_p", "top_k", "chat_template_kwargs", "seed")
        )
    ):
        raise ValueError("Astra does not support sampling or thinking-budget overrides")
    effort = request.reasoning_effort or model.config.reasoning_effort
    if effort is None:
        raise ValueError("Astra reasoning effort must be explicit")
    payload: dict[str, Any] = {
        "model": model.config.model,
        "input": encode_input(request.messages),
        "max_output_tokens": request.max_tokens,
        "reasoning": {"effort": effort},
        "store": False,
        "include": ["reasoning.encrypted_content"],
    }
    if request.tools:
        payload["tools"] = []
        for tool in request.tools:
            if tool.get("type") != "function" or "function" not in tool:
                raise ValueError("expected a function tool specification")
            payload["tools"].append({"type": "function", **tool["function"]})
    started = time.perf_counter()
    raw = post_json(
        f"{model.config.base_url.rstrip('/')}/responses",
        payload,
        model._headers(),
        model.config.timeout_seconds,
    )
    if (raw.get("reasoning") or {}).get("effort") != effort:
        raise ValueError("response did not confirm the requested reasoning effort")
    status = raw.get("status")
    if status not in ("completed", "incomplete"):
        raise RuntimeError(f"response did not complete: {status}")
    output = tuple(raw.get("output") or ())
    calls = tuple(
        ToolCall(
            id=item["call_id"], name=item["name"], arguments=_parse_args(item.get("arguments"))
        )
        for item in output
        if item.get("type") == "function_call"
    )
    content = "".join(
        block.get("text", block.get("refusal", ""))
        for item in output
        if item.get("type") == "message"
        for block in item.get("content", ())
    )
    usage = raw.get("usage") or {}
    return Completion(
        message=Message(role="assistant", content=content, tool_calls=calls, response_items=output),
        usage=Usage(
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            wall_seconds=time.perf_counter() - started,
        ),
        finish_reason="length" if status == "incomplete" else "tool_calls" if calls else "stop",
        raw=raw,
    )
