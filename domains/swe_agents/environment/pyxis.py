"""Persistent Pyxis sessions: one Slurm allocation and private image per episode.

Invoke on the cluster login host. Normal queue waiting is allowed. Never preflight
namespaces in the submitting SSH shell: Pyxis has its own supported launch context.
"""

import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from domains.swe_agents.environment.enroot import EnrootSession
from domains.swe_agents.environment.runtime import RuntimeUnavailable


class PyxisRuntime:
    """Allocate only explicitly bounded resources; unnamed images disappear with the job."""

    def __init__(
        self,
        *,
        seconds: int = 120,
        cpus: int = 1,
        memory_mb: int = 1024,
        startup_timeout: float = 1800,
        executable: str = "srun",
    ) -> None:
        if any(type(v) is not int or v <= 0 for v in (seconds, cpus, memory_mb)):
            raise ValueError("runtime resource limits must be positive integers")
        if startup_timeout <= 0:
            raise ValueError("startup timeout must be positive")
        self.seconds, self.cpus, self.memory_mb = seconds, cpus, memory_mb
        self.startup_timeout, self.executable = startup_timeout, executable

    def argv(self, image: str, workdir: str, python_env: str = "image") -> list[str]:
        source = Path(__file__).with_name("pyxis_worker.py").read_text()
        command = ["python", "-u", "-c", source]
        if python_env == "conda_testbed":
            command = [
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-c",
                "set -e; source /opt/miniconda3/etc/profile.d/conda.sh; "
                "conda activate testbed; exec " + shlex.join(command),
            ]
        elif python_env != "image":
            raise ValueError("unsupported Python environment")
        return [
            self.executable,
            "--nodes=1",
            "--ntasks=1",
            f"--cpus-per-task={self.cpus}",
            f"--mem={self.memory_mb}M",
            f"--time={self.seconds // 60}:{self.seconds % 60:02d}",
            "--exclude=worker-4,worker-5",
            "--qos=guest-dev",
            "--job-name=pcode-episode",
            "--export=NONE",
            f"--container-image={image}",
            f"--container-workdir={workdir}",
            "--container-writable",
            "--container-remap-root",
            "--no-container-mount-home",
            "--no-container-entrypoint",
            *command,
        ]

    def launch(
        self,
        image: str,
        workdir: str = "/",
        *,
        python_env: str = "image",
    ) -> "PyxisSession":
        """Start a broker for infrastructure checks; task runs must use start to bind a pin."""
        path = Path(image)
        if not path.is_absolute() or not path.is_file():
            raise RuntimeUnavailable("an existing absolute squashfs path is required")
        if not workdir.startswith("/") or "\x00" in workdir:
            raise ValueError("workdir must be an absolute path")
        return PyxisSession(self.argv(str(path), workdir, python_env), self.startup_timeout)

    def start(
        self,
        image: str | None,
        url: str,
        commit: str,
        *,
        workdir: str | None = None,
        python_env: str = "image",
    ) -> "PyxisSession":
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("commit must be an immutable full revision")
        name = Path(urlparse(url).path).name.removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
            raise ValueError("cannot derive a safe repository path from the URL")
        if image is None:
            raise RuntimeUnavailable("a pinned image is required")
        session = self.launch(image, workdir or "/" + name, python_env=python_env)
        try:
            session._checked(f"git checkout --detach {shlex.quote(commit)}", 120)
            if session._checked("git rev-parse HEAD", 30).strip() != commit:
                raise RuntimeUnavailable("image did not check out the pinned revision")
            if session._checked("git status --porcelain --untracked-files=no", 30).strip():
                raise RuntimeUnavailable("pinned checkout contains tracked modifications")
            session._baseline = session._files()
            session._packages = session._installed()
            return session
        except BaseException:
            session.stop()
            raise


class PyxisSession(EnrootSession):
    """Reuse file/audit operations, replacing enroot commands with one persistent broker."""

    def __init__(self, argv: list[str], startup_timeout: float) -> None:
        self.closed = False
        self._baseline: dict[str, str] = {}
        self._packages: dict[str, str] = {}
        self._buffer = bytearray()
        self._log = tempfile.TemporaryFile()
        # Do not inherit API credentials, SLURM_IMMEDIATE or an unrelated allocation ID.
        env = {
            k: os.environ[k] for k in ("PATH", "HOME", "USER", "LOGNAME", "LANG") if k in os.environ
        }
        try:
            self.process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                env=env,
                bufsize=0,
                start_new_session=True,
            )
        except BaseException:
            self._log.close()
            raise
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            self.attestation = self._exchange(None, startup_timeout)
            if self.attestation.get("ready") is not True:
                raise RuntimeUnavailable("broker did not initialize")
        except BaseException:
            self.stop()
            raise

    def _exchange(self, request: dict | None, timeout: float) -> dict:
        if self.closed:
            raise RuntimeError("session is closed")
        data = b"" if request is None else (json.dumps(request, allow_nan=False) + "\n").encode()
        if len(data) > 2_000_000:
            raise RuntimeUnavailable("runtime request exceeded protocol limit")
        offset = 0
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if data:
                selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeUnavailable("runtime broker timed out")
                for key, _ in selector.select(remaining):
                    if key.fileobj is self.process.stdin:
                        offset += os.write(key.fd, data[offset : offset + 65536])
                        if offset == len(data):
                            selector.unregister(self.process.stdin)
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            raise RuntimeUnavailable(
                                "runtime broker exited: " + self.logs()[-2000:]
                            )
                        self._buffer.extend(chunk)
                        if len(self._buffer) > 50_000_000:
                            raise RuntimeUnavailable("runtime reply exceeded protocol limit")
                        if b"\n" in self._buffer:
                            line, tail = self._buffer.split(b"\n", 1)
                            self._buffer = bytearray(tail)
                            if tail or offset != len(data):
                                raise RuntimeUnavailable("unexpected broker output")
                            value = json.loads(line)
                            if not isinstance(value, dict):
                                raise RuntimeUnavailable("invalid broker reply")
                            return value

    def exec(self, command: str, timeout: float) -> tuple[int, str, str]:
        if not 0 < timeout <= 3600:
            raise ValueError("command timeout must be in (0, 3600]")
        try:
            reply = self._exchange({"command": command, "timeout": timeout}, timeout + 5)
            if "error" in reply:
                raise RuntimeUnavailable(reply["error"])
            if (
                set(reply) != {"exit", "stdout", "stderr"}
                or type(reply["exit"]) is not int
                or not all(isinstance(reply[k], str) for k in ("stdout", "stderr"))
            ):
                raise RuntimeUnavailable("invalid command result")
            return reply["exit"], reply["stdout"], reply["stderr"]
        except BaseException:
            self.stop()
            raise

    def logs(self) -> str:
        # pread avoids moving the descriptor offset while srun is still writing.
        size = os.fstat(self._log.fileno()).st_size
        return os.pread(self._log.fileno(), min(size, 65536), max(0, size - 65536)).decode(
            errors="replace"
        )

    def stop(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            # EOF asks the trusted broker to exit; srun then releases the allocation.
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGINT)
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
        finally:
            self.process.stdout.close()
            self._log.close()
