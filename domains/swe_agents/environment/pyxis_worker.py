"""Trusted stdlib-only command broker, kept alive inside one Slurm task.

This provides task lifecycle management, not isolation from a malicious task process.
Oracle verification must run separately against trusted test inputs.
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import socket
import subprocess
import sys
import time

LIMIT = 4_000_000


def execute(command: str, timeout: float) -> dict[str, int | str]:
    process = subprocess.Popen(
        ["/bin/bash", "--noprofile", "--norc", "-c", command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("task command timed out")
                for key, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output[key.data].extend(chunk)
                        if len(output[key.data]) > LIMIT:
                            raise ValueError("task output exceeded audit limit")
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return {
            "exit": process.returncode,
            **{name: value.decode(errors="replace") for name, value in output.items()},
        }
    finally:
        # Background jobs must not survive to mutate the next command's state.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


def main() -> None:
    print(
        json.dumps(
            {
                "ready": True,
                "host": socket.gethostname(),
                "job_id": os.environ.get("SLURM_JOB_ID"),
                "workdir": os.getcwd(),
            }
        ),
        flush=True,
    )
    while True:
        line = sys.stdin.buffer.readline(2_000_001)
        if not line:
            return
        if len(line) > 2_000_000 or not line.endswith(b"\n"):
            raise ValueError("invalid request size")
        request = json.loads(line)
        if request == {"stop": True}:
            return
        try:
            timeout = request["timeout"]
            if not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600:
                raise ValueError("invalid timeout")
            result = execute(request["command"], timeout)
        except Exception as exc:
            result = {"error": type(exc).__name__ + ": " + str(exc)}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
