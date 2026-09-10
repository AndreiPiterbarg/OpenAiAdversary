"""A served engine (vLLM, SGLang, or anything speaking the OpenAI chat-completions API).

This is the intended path for the 27B target on a rented GPU: the weights are open, so the
licence class must be explicitly declared before outputs may be reused. Vendor APIs reuse
the same wire
format but are wrapped separately in :mod:`adversary.execution.backends.frontier` so their
restricted licence cannot be forgotten.
"""

import json
import os
import time
from typing import Any, Literal

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
from adversary.execution.http import post_json


class ServedConfig(StrictModel):
    """Connection details for an OpenAI-compatible endpoint."""

    base_url: str = Field(description="e.g. 'http://gpu-box:8000/v1'")
    model: str = Field(description="Model name as the server knows it")
    version: str = Field(default="", description="Checkpoint or adapter revision, for provenance")
    api_key_env: str | None = Field(
        default=None, description="Environment variable holding the key"
    )
    license: LicenseClass = Field(default=LicenseClass.RESTRICTED)
    timeout_seconds: float = Field(default=600.0, gt=0)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    sampling_supported: bool = True
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


@MODELS.register("served")
class ServedModel(LanguageModel):
    """Chat completions over HTTP with no SDK dependency."""

    backend_name = "served"

    def __init__(self, **config: Any) -> None:
        self.config = ServedConfig(**config)
        self._info = ModelInfo(
            id=self.config.model,
            version=self.config.version,
            license=self.config.license,
            backend=self.backend_name,
        )

    @property
    def info(self) -> ModelInfo:
        return self._info

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.api_key_env:
            key = os.environ.get(self.config.api_key_env)
            if not key:
                raise RuntimeError(f"{self.config.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def complete(self, request: CompletionRequest) -> Completion:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [self._encode(m) for m in request.messages],
            self.config.token_parameter: request.max_tokens,
        }
        if request.thinking_budget is not None:
            raise ValueError("thinking_budget is unsupported by this transport")
        if self.config.sampling_supported:
            payload["temperature"] = request.temperature
            for key in ("top_p", "top_k", "chat_template_kwargs"):
                value = getattr(request, key)
                if value is not None:
                    payload[key] = value
        elif request.temperature != 0 or any(
            getattr(request, key) is not None
            for key in ("top_p", "top_k", "chat_template_kwargs", "seed")
        ):
            raise ValueError("sampling overrides are unsupported by this model")
        effort = request.reasoning_effort or self.config.reasoning_effort
        if effort is not None:
            payload["reasoning_effort"] = effort
        if request.tools:
            payload["tools"] = list(request.tools)
        if request.seed is not None:
            payload["seed"] = request.seed
        raw = post_json(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            payload,
            self._headers(),
            self.config.timeout_seconds,
        )
        choice = raw["choices"][0]
        message = choice["message"]
        tool_calls = tuple(
            ToolCall(
                id=c["id"],
                name=c["function"]["name"],
                arguments=_parse_args(c["function"].get("arguments")),
            )
            for c in message.get("tool_calls") or ()
        )
        usage = raw.get("usage") or {}
        return Completion(
            message=Message(
                role="assistant", content=message.get("content") or "", tool_calls=tool_calls
            ),
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                wall_seconds=time.perf_counter() - started,
            ),
            finish_reason=str(choice.get("finish_reason", "stop")),
            raw=raw,
        )

    @staticmethod
    def _encode(message: Message) -> dict[str, Any]:
        encoded: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            encoded["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": _dump_args(c.arguments)},
                }
                for c in message.tool_calls
            ]
        if message.tool_call_id:
            encoded["tool_call_id"] = message.tool_call_id
        return encoded


def _parse_args(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _dump_args(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments)
