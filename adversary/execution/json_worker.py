"""Bounded JSON IPC for isolated workers; no inherited secrets or unconfined fallback."""

import json
import math
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class WorkerError(RuntimeError):
    """The isolated operation did not produce valid evidence."""


class JsonWorker:
    def __init__(self, module: str, timeout: float = 5.0) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.module, self.timeout = module, timeout
        self._process: subprocess.Popen | None = None
        self._closed = False

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._process is not None or self._closed:
            raise WorkerError("worker must be prepared exactly once")
        if sys.platform != "linux":
            raise WorkerError("program confinement requires Linux seccomp")
        root = str(Path(__file__).resolve().parents[2])
        bootstrap = (
            f"import sys,runpy;sys.path.insert(0,{root!r});"
            f"runpy.run_module({self.module!r},run_name='__main__')"
        )
        self._process = subprocess.Popen(
            [sys.executable, "-I", "-c", bootstrap],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            start_new_session=True,
        )
        assert self._process.stdin is not None and self._process.stdout is not None
        os.set_blocking(self._process.stdin.fileno(), False)
        os.set_blocking(self._process.stdout.fileno(), False)
        return self._exchange(payload)

    def _exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or self._closed:
            raise WorkerError("program worker is not running")
        assert process.stdin is not None and process.stdout is not None
        try:
            data = (json.dumps(payload, allow_nan=False) + "\n").encode()
            if len(data) > 2_000_000:
                raise WorkerError("worker input exceeded the protocol limit")
            offset = 0
            output = bytearray()
            deadline = time.monotonic() + self.timeout
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdin, selectors.EVENT_WRITE)
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WorkerError("program worker timed out")
                    events = selector.select(remaining)
                    for key, _ in events:
                        if key.fileobj is process.stdin:
                            offset += os.write(
                                process.stdin.fileno(), data[offset : offset + 65536]
                            )
                            if offset == len(data):
                                selector.unregister(process.stdin)
                        else:
                            chunk = os.read(process.stdout.fileno(), 65536)
                            if not chunk:
                                raise WorkerError("program worker exited without a reply")
                            output.extend(chunk)
                            if len(output) > 1_100_000:
                                raise WorkerError("worker output exceeded the protocol limit")
                            if b"\n" in output:
                                line, tail = output.split(b"\n", 1)
                                if tail or offset != len(data):
                                    raise WorkerError("unexpected worker protocol output")
                                result = json.loads(line)
                                if not isinstance(result, dict):
                                    raise WorkerError("invalid worker response")
                                return result
        except Exception as exc:
            self.close()
            if isinstance(exc, WorkerError):
                raise
            raise WorkerError(f"worker protocol failed: {type(exc).__name__}") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.kill()
        process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
