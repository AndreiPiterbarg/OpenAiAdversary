"""Frontier vendor APIs, used for transfer checks only.

Every class here is ``RESTRICTED`` and cannot be configured otherwise: vendor terms bar using
outputs to build competing models, and a customer's model is a competitor by definition. The
repair layer and the probe library check :attr:`ModelInfo.shippable`, so wiring a frontier
model into the wrong place fails at construction rather than at a lawyer's desk.
"""

import os
import time
from typing import Any

from pydantic import Field

from adversary.core.config import StrictModel
from adversary.core.model import (
    Completion,
    CompletionRequest,
    LanguageModel,
    LicenseClass,
    Message,
    ModelInfo,
    ToolCall,
    Usage,
)
from adversary.execution.backends import MODELS
from adversary.execution.backends.openai_compatible import ServedModel
from adversary.execution.backends.responses import complete_responses
from adversary.execution.http import post_json


@MODELS.register("openai")
class OpenAIModel(ServedModel):
    """OpenAI chat completions. Restricted licence, fixed."""

    backend_name = "openai"

    def __init__(self, model: str, api_key_env: str = "OPENAI_API_KEY", **config: Any) -> None:
        config.pop("license", None)
        if model == "gpt-6-astra" or model.startswith("gpt-6-astra-"):
            config.setdefault("reasoning_effort", "low")
        super().__init__(
            base_url=config.pop("base_url", "https://api.openai.com/v1"),
            model=model,
            api_key_env=api_key_env,
            license=LicenseClass.RESTRICTED,
            **config,
        )

    def complete(self, request: CompletionRequest) -> Completion:
        if self.config.model == "gpt-6-astra" or self.config.model.startswith("gpt-6-astra-"):
            return complete_responses(self, request)
        return super().complete(request)


@MODELS.register("gemini")
class GeminiModel(ServedModel):
    """Gemini through its OpenAI-compatible endpoint. Restricted licence, fixed."""

    backend_name = "gemini"

    def __init__(self, model: str, api_key_env: str = "GEMINI_API_KEY", **config: Any) -> None:
        config.pop("license", None)
        super().__init__(
            base_url=config.pop(
                "base_url", "https://generativelanguage.googleapis.com/v1beta/openai"
            ),
            model=model,
            api_key_env=api_key_env,
            license=LicenseClass.RESTRICTED,
            **config,
        )


class AnthropicConfig(StrictModel):
    """Anthropic Messages API connection."""

    model: str = Field(description="e.g. 'claude-sonnet-5'")
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"
    timeout_seconds: float = Field(default=600.0, gt=0)


def anthropic_tools(tools: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """OpenAI function specs to Anthropic tool specs; specs already in that shape pass through."""
    out = []
    for tool in tools:
        function = tool.get("function")
        if function is not None:
            out.append(
                {
                    "name": function["name"],
                    "description": function.get("description", ""),
                    "input_schema": function.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                }
            )
        else:
            out.append(dict(tool))
    return out


def anthropic_messages(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
    """Encode a conversation for the Messages API.

    Assistant tool calls become ``tool_use`` blocks; tool results become ``tool_result``
    blocks inside a user turn, with consecutive results merged into one turn so roles
    alternate as the API requires. System turns are excluded (sent as ``system``).
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for call in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                )
            out.append({"role": "assistant", "content": blocks or m.content})
        elif m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            previous = out[-1] if out else None
            if (
                previous is not None
                and previous["role"] == "user"
                and isinstance(previous["content"], list)
                and previous["content"]
                and previous["content"][0].get("type") == "tool_result"
            ):
                previous["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        else:
            out.append({"role": "user", "content": m.content})
    return out


@MODELS.register("anthropic")
class AnthropicModel(LanguageModel):
    """Anthropic Messages API. Restricted licence, fixed."""

    def __init__(self, **config: Any) -> None:
        self.config = AnthropicConfig(**config)
        self._info = ModelInfo(
            id=self.config.model,
            version=self.config.api_version,
            license=LicenseClass.RESTRICTED,
            backend="anthropic",
        )

    @property
    def info(self) -> ModelInfo:
        return self._info

    def complete(self, request: CompletionRequest) -> Completion:
        key = os.environ.get(self.config.api_key_env)
        if not key:
            raise RuntimeError(f"{self.config.api_key_env} is not set")
        started = time.perf_counter()
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": request.max_tokens,
            "messages": anthropic_messages(request.messages),
        }
        if system:
            payload["system"] = system
        if request.tools:
            payload["tools"] = anthropic_tools(request.tools)
        if request.thinking_budget:
            # Extended thinking requires temperature 1; the budget must leave room to answer.
            payload["thinking"] = {"type": "enabled", "budget_tokens": request.thinking_budget}
            payload["temperature"] = 1.0
            payload["max_tokens"] = max(request.max_tokens, request.thinking_budget + 1)
        else:
            payload["temperature"] = request.temperature
        raw = post_json(
            f"{self.config.base_url.rstrip('/')}/v1/messages",
            payload,
            {"x-api-key": key, "anthropic-version": self.config.api_version},
            self.config.timeout_seconds,
        )
        text = "".join(
            block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text"
        )
        tool_calls = tuple(
            ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {})
            for block in raw.get("content", [])
            if block.get("type") == "tool_use"
        )
        usage = raw.get("usage") or {}
        return Completion(
            message=Message(role="assistant", content=text, tool_calls=tool_calls),
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                wall_seconds=time.perf_counter() - started,
            ),
            finish_reason=str(raw.get("stop_reason", "stop")),
            raw=raw,
        )
