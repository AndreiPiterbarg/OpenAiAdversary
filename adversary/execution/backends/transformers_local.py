"""Local ``transformers`` checkpoint behind the model boundary.

For small models on a laptop (MPS or CPU) and for the LoRA-adapted target on a GPU box when a
serving engine is not warranted. Imports ``torch`` and ``transformers`` lazily so the rest of
the system loads without them. Tool calls are parsed from ``<tool_call>{json}</tool_call>``
blocks, the Hermes/Qwen convention; models using another convention should be served through
an engine that parses their format (the ``served`` backend). Not safe for concurrent calls.
"""

import json
import re
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
from adversary.core.util import short_id
from adversary.execution.backends import MODELS

_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


class TransformersConfig(StrictModel):
    """How to load a local checkpoint."""

    model_id: str = Field(description="Hub id or local path")
    revision: str = Field(default="main", description="Hub revision or adapter tag")
    device: str = Field(default="auto", description="'auto', 'cpu', 'mps' or 'cuda'")
    dtype: str = Field(default="bfloat16", description="torch dtype name")
    license: LicenseClass = Field(
        default=LicenseClass.RESTRICTED, description="Re-use rights must be explicitly declared"
    )
    trust_remote_code: bool = False


def parse_tool_calls(text: str) -> tuple[str, tuple[ToolCall, ...]]:
    """Split Hermes/Qwen-style ``<tool_call>`` blocks out of generated text."""
    calls: list[ToolCall] = []
    for match in _TOOL_CALL.finditer(text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        name = payload.get("name")
        if not isinstance(name, str):
            continue
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {"_raw": arguments}
        calls.append(
            ToolCall(
                id=short_id("call", [name, arguments, len(calls)]), name=name, arguments=arguments
            )
        )
    content = _TOOL_CALL.sub("", text).strip()
    return content, tuple(calls)


@MODELS.register("transformers")
class TransformersModel(LanguageModel):
    """Greedy or sampled chat completion with a local checkpoint."""

    def __init__(self, **config: Any) -> None:
        self.config = TransformersConfig(**config)
        self._info = ModelInfo(
            id=self.config.model_id,
            version=self.config.revision,
            license=self.config.license,
            backend="transformers",
        )
        self._model = None
        self._tokenizer = None

    @property
    def info(self) -> ModelInfo:
        return self._info

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = self.config.device
        if device == "auto":
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if torch.backends.mps.is_available()
                else "cpu"
            )
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_id,
            revision=self.config.revision,
            trust_remote_code=self.config.trust_remote_code,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.config.model_id,
            revision=self.config.revision,
            dtype=getattr(torch, self.config.dtype),
            trust_remote_code=self.config.trust_remote_code,
        ).to(device)
        self._model.eval()

    @staticmethod
    def _chat(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
        chat: list[dict[str, Any]] = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {"type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in m.tool_calls
                ]
            chat.append(entry)
        return chat

    def complete(self, request: CompletionRequest) -> Completion:
        if request.reasoning_effort is not None or request.thinking_budget is not None:
            raise ValueError("local generation does not support reasoning controls")
        if self._model is None:
            self._load()
        assert self._model is not None and self._tokenizer is not None
        import torch

        started = time.perf_counter()
        tools = [dict(t) for t in request.tools] or None
        encoded = self._tokenizer.apply_chat_template(
            self._chat(request.messages),
            tools=tools,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
            **(request.chat_template_kwargs or {}),
        )
        input_ids = encoded["input_ids"].to(self._model.device)
        attention_mask = encoded.get("attention_mask")
        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": request.max_tokens,
            "do_sample": request.temperature > 0,
            "pad_token_id": self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
        }
        if request.temperature > 0:
            generate_kwargs["temperature"] = request.temperature
            if request.top_p is not None:
                generate_kwargs["top_p"] = request.top_p
            if request.top_k is not None:
                generate_kwargs["top_k"] = max(0, request.top_k)
        if attention_mask is not None:
            generate_kwargs["attention_mask"] = attention_mask.to(self._model.device)
        devices = [self._model.device] if self._model.device.type == "cuda" else []
        with torch.random.fork_rng(devices=devices), torch.no_grad():
            if request.seed is not None:
                torch.manual_seed(request.seed)
            output = self._model.generate(input_ids, **generate_kwargs)
        new_tokens = output[0][input_ids.shape[1] :]
        text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        content, tool_calls = parse_tool_calls(text)
        usage = Usage(
            input_tokens=int(input_ids.shape[1]),
            output_tokens=int(new_tokens.shape[0]),
            wall_seconds=time.perf_counter() - started,
        )
        return Completion(
            message=Message(role="assistant", content=content, tool_calls=tool_calls), usage=usage
        )
