"""One explicit, small model request; never a task episode or an oracle result.

The input byte limit controls request size, not total token usage. The output
limit includes reasoning tokens; callers must retain actual returned usage.
This helper does not alter the environment's protected-oracle or budget gates.
"""

import json
import os
from typing import Any

from adversary.core.model import Completion, CompletionRequest
from adversary.execution.backends.frontier import OpenAIModel
from domains.swe_agents.environment.factory_verifier import admit_restricted_sources

MAX_INPUT_BYTES = 8192


class ModelSmokeError(RuntimeError):
    """The single attempt failed; no automatic retry has been made."""


def render_restricted_candidate(
    response_text: str, pristine_sources: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Render one finite-grammar choice, never model-supplied Python source.

    The caller supplies package sources captured from the verified pristine image.
    Admission checks the frozen declarations digest and preserves the source closure.
    The returned admission is a grammar receipt, not a test or clean-solve verdict.
    """
    if type(response_text) is not str:
        raise ValueError("repair choice must be JSON text")
    try:
        size = len(response_text.encode("utf-8"))
    except UnicodeError:
        raise ValueError("repair choice must be valid UTF-8") from None
    if size > 512:
        raise ValueError("repair choice exceeds byte bound")

    def unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate repair choice key")
            value[key] = item
        return value

    try:
        choice = json.loads(response_text, object_pairs_hook=unique)
    except (ValueError, RecursionError):
        raise ValueError("repair choice must be one strict JSON object") from None
    if type(choice) is not dict or set(choice) != {"method", "keyword"}:
        raise ValueError("repair choice requires exactly method and keyword")
    if (
        type(choice["method"]) is not str
        or choice["method"] not in ("evaluate", "evaluate_pre")
        or type(choice["keyword"]) is not str
        or choice["keyword"] not in ("extra", "overrides")
    ):
        raise ValueError("repair choice is outside the finite grammar")
    path = "factory/declarations.py"
    if type(pristine_sources) is not dict or type(pristine_sources.get(path)) is not str:
        raise ValueError("pristine declarations source required")
    base_line = "        choice = self.decider.evaluate(instance=instance, step=step, extra={})\n"
    line = (
        f"        choice = self.decider.{choice['method']}"
        f"(instance=instance, step=step, {choice['keyword']}={{}})\n"
    )
    candidate = dict(pristine_sources)
    candidate[path] = pristine_sources[path].replace(base_line, line, 1)
    admission = admit_restricted_sources(pristine_sources, candidate)
    return candidate, admission


def model_smoke(request: CompletionRequest) -> Completion:
    """Send exactly one text-only Astra request after validating its small bounds.

    Supply a prebuilt request with max_tokens=256 (or 512) and low effort. This
    function neither prints credentials nor reads repository files into a prompt.
    A truncated response is returned as such, without continuation or retry.
    """
    if not isinstance(request, CompletionRequest):
        raise ValueError("smoke requires a prebuilt CompletionRequest")
    if type(request.max_tokens) is not int or request.max_tokens not in (256, 512):
        raise ValueError("smoke output cap must be 256 or 512 tokens")
    if request.reasoning_effort not in (None, "low"):
        raise ValueError("smoke requires low reasoning effort")
    if request.tools or not 1 <= len(request.messages) <= 4:
        raise ValueError("smoke requires one to four text messages without tools")
    if any(
        message.role not in ("system", "user")
        or message.tool_calls
        or message.tool_call_id is not None
        or message.response_items
        for message in request.messages
    ):
        raise ValueError("smoke accepts only ordinary system and user text")
    if not any(message.role == "user" and message.content.strip() for message in request.messages):
        raise ValueError("smoke requires nonempty user text")
    try:
        size = sum(len(message.content.encode("utf-8")) for message in request.messages)
    except UnicodeError:
        raise ValueError("smoke input must be valid UTF-8") from None
    if size > MAX_INPUT_BYTES:
        raise ValueError("smoke input exceeds byte limit")
    if request.temperature != 0 or any(
        getattr(request, field) is not None
        for field in ("top_p", "top_k", "chat_template_kwargs", "seed", "thinking_budget")
    ):
        raise ValueError("smoke does not support sampling or thinking-budget overrides")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise ModelSmokeError("OPENAI_API_KEY is not set; no request made")
    model = OpenAIModel(model="gpt-6-astra", reasoning_effort="low", timeout_seconds=120)
    try:
        result = model.complete(request.model_copy(update={"reasoning_effort": "low"}))
    except Exception:
        # Transport errors can contain arbitrary response bodies. Avoid exposing
        # those (or credentials echoed by a failed endpoint) in a traceback.
        raise ModelSmokeError("single smoke request failed; no retry attempted") from None
    usage = result.raw.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(field)) is not int or usage[field] < 0
        for field in ("input_tokens", "output_tokens")
    ):
        raise ModelSmokeError("smoke response lacks measured token usage; no retry attempted")
    return result
