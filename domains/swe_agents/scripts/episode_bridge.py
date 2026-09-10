"""Bounded local API bridge for an already preflighted remote episode controller.

Request byte limits are not total-token or monetary guarantees. No retries are
made: a failed API attempt may have unknown billed usage and stops the bridge.
"""

import json
import os
import re
import selectors
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from adversary.core.model import CompletionRequest
from adversary.execution.backends.frontier import OpenAIModel
from domains.swe_agents.environment.prun_integrity import strict_json

LINE_LIMIT = 2_000_000
REQUEST_LIMIT = 32768


class BridgeError(RuntimeError):
    """Sanitized bridge failure; inspect the bounded ledger for its stage."""


def _encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode()


def _write(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(_encode(value))
        handle.flush()
        os.fsync(handle.fileno())


def _lines(stream: BinaryIO) -> Iterator[str]:
    pending = bytearray()
    os.set_blocking(stream.fileno(), False)
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while True:
            if not selector.select(1800):
                raise BridgeError("controller output timed out")
            chunk = os.read(stream.fileno(), 65536)
            if not chunk:
                if pending:
                    raise BridgeError("controller ended with partial JSON line")
                return
            pending.extend(chunk)
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending = bytearray(rest)
                if len(line) > LINE_LIMIT:
                    raise BridgeError("controller line exceeds byte limit")
                yield line.decode("utf-8")
            if len(pending) > LINE_LIMIT:
                raise BridgeError("controller line exceeds byte limit")


def _send(stream: BinaryIO, payload: dict) -> None:
    data = _encode(payload)
    if len(data) > LINE_LIMIT:
        raise BridgeError("completion exceeds bridge byte limit")
    os.set_blocking(stream.fileno(), False)
    deadline = time.monotonic() + 120
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_WRITE)
        offset = 0
        while offset < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise BridgeError("controller input timed out")
            offset += os.write(stream.fileno(), data[offset : offset + 65536])


def _request(
    event: dict,
    episodes: dict[str, tuple[int, int]],
    maxepisodes: int,
    *,
    call_limit: int = 8,
    output_limit: int = 8192,
    request_byte_limit: int = REQUEST_LIMIT,
) -> CompletionRequest:
    if type(request_byte_limit) is not int or not 1 <= request_byte_limit <= LINE_LIMIT:
        raise BridgeError("invalid request byte limit")
    if set(event) != {"event", "request", "episode_id", "call"}:
        raise BridgeError("invalid model request event fields")
    episode = event["episode_id"]
    if type(episode) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", episode):
        raise BridgeError("invalid episode identity")
    previous = episodes.get(episode, (0, 0))
    if episode not in episodes and len(episodes) >= maxepisodes:
        raise BridgeError("episode limit reached")
    if (
        type(event["call"]) is not int
        or event["call"] != previous[0] + 1
        or event["call"] > call_limit
    ):
        raise BridgeError("invalid or excessive episode call index")
    raw = event["request"]
    if type(raw) is not dict or len(_encode(raw)) > request_byte_limit:
        raise BridgeError("model request exceeds byte limit or has invalid type")
    cap = raw.get("max_tokens")
    if type(cap) is not int or not 1 <= cap <= 1024 or previous[1] + cap > output_limit:
        raise BridgeError("requested output exceeds episode bound")
    request = CompletionRequest.model_validate(raw)
    if (
        request.reasoning_effort not in (None, "low")
        or request.temperature != 0
        or any(
            getattr(request, name) is not None
            for name in ("top_p", "top_k", "seed", "chat_template_kwargs", "thinking_budget")
        )
    ):
        raise BridgeError("unsupported decoding configuration")
    names = []
    for tool in request.tools:
        if tool.get("type") != "function" or set(tool) != {"type", "function"}:
            raise BridgeError("unsupported tool schema")
        function = tool["function"]
        if type(function) is not dict or function.get("name") not in {"shell", "submit"}:
            raise BridgeError("tool is outside episode allowlist")
        if (
            not set(function) <= {"name", "description", "parameters", "strict"}
            or type(function.get("parameters")) is not dict
        ):
            raise BridgeError("unsupported function schema fields")
        names.append(function["name"])
    if len(set(names)) != len(names):
        raise BridgeError("duplicate tool schema")
    if not request.messages:
        raise BridgeError("empty model transcript")
    episodes[episode] = (event["call"], previous[1] + cap)
    return request.model_copy(update={"reasoning_effort": "low"})


def run_bridge(
    argv: list[str],
    out: Path,
    maxepisodes: int = 1,
    *,
    call_limit: int = 8,
    output_limit: int = 8192,
    request_byte_limit: int = REQUEST_LIMIT,
) -> dict:
    """Run a trusted caller's controller argv; never place API keys in its environment.

    The caller owns protected-verifier preflight and negative gates. Output files
    record requests before spending and completions before remote forwarding.
    """
    if type(maxepisodes) is not int or maxepisodes not in (1, 4, 5, 20):
        raise ValueError("maxepisodes must be explicitly 1, 4, 5 or 20")
    if (
        type(call_limit) is not int
        or not 1 <= call_limit <= 100
        or type(output_limit) is not int
        or not 1 <= output_limit <= 102400
        or type(request_byte_limit) is not int
        or not 1 <= request_byte_limit <= 1000000
    ):
        raise ValueError("invalid explicit bridge bounds")
    if (
        not isinstance(argv, list)
        or not argv
        or any(type(a) is not str or "\x00" in a for a in argv)
    ):
        raise ValueError("trusted subprocess argv required")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key.strip():
        raise BridgeError("OPENAI_API_KEY is not set; no request made")
    if any(key in arg for arg in argv):
        raise BridgeError("credentials must not appear in controller argv")
    out = Path(out)
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    model = OpenAIModel(model="gpt-6-astra", reasoning_effort="low", timeout_seconds=120)
    episodes = {}
    process = None
    attempts = 0
    usage = {"input_tokens": 0, "output_tokens": 0}
    stage = "controller_start"
    attempted_call = False
    usage_known = False
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
            stage, attempted_call, usage_known = "controller_event", False, False
            if key in text:
                raise BridgeError("credential-like controller output refused")
            event = strict_json(text)
            if type(event) is not dict or type(event.get("event")) is not str:
                raise BridgeError("invalid controller event")
            if key in _encode(event).decode():
                raise BridgeError("credential-like controller output refused")
            if event["event"] != "model_request":
                _write(out / f"event-{number:06d}.json", event)
                continue
            stage = "request_validation"
            request = _request(
                event,
                episodes,
                maxepisodes,
                call_limit=call_limit,
                output_limit=output_limit,
                request_byte_limit=request_byte_limit,
            )
            stem = f"call-{attempts + 1:04d}"
            _write(out / f"{stem}-request.json", event)
            stage, attempted_call = "model_call", True
            attempts += 1
            result = model.complete(request)
            raw_usage = result.raw.get("usage")
            if not isinstance(raw_usage, dict) or any(
                type(raw_usage.get(name)) is not int or raw_usage[name] < 0 for name in usage
            ):
                raise BridgeError("model response has no measured usage")
            usage_known = True
            for name in usage:
                usage[name] += raw_usage[name]
            completion = result.model_dump(mode="json")
            if key in _encode(completion).decode():
                raise BridgeError("credential-like model output refused")
            _write(out / f"{stem}-completion.json", completion)
            stage = "completion_forward"
            _send(process.stdin, completion)
        stage = "controller_exit"
        process.stdin.close()
        if process.wait(timeout=10) != 0:
            raise BridgeError("controller exited unsuccessfully")
        result = {
            "status": "complete",
            "model_calls": attempts,
            "episodes": len(episodes),
            "usage": usage,
            "total_token_bound": None,
        }
        _write(out / "summary.json", result)
        return result
    except BaseException:
        failure = {
            "status": "failed",
            "stage": stage,
            "model_calls": attempts,
            "measured_usage": usage,
            "billing_unknown": attempted_call and not usage_known,
            "retry_attempted": False,
        }
        _write(out / "failure.json", failure)
        raise BridgeError(f"episode bridge failed at {stage}; no retry attempted") from None
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
