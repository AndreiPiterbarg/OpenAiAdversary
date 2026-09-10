"""Fresh host copies and bounded command transport; no container isolation claim.

This adapter deliberately has no default model-execution boundary. A trusted caller
must supply a separately reviewed host filesystem/resource guard. The container
Landlock policy alone is insufficient on a shared host.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session


@dataclass(frozen=True)
class HostRuntimePin:
    task_key: str
    commit: str
    repository: Path
    repository_sha256: str
    venv: Path
    venv_sha256: str
    system_python: Path
    kind: str = "interactive_host_runtime_v1"


def tree_digest(root: Path, *, allow_system_links: bool = False) -> str:
    """Hash path names, modes, links and bytes without following directory links."""
    if not root.is_absolute() or root.resolve() != root or not root.is_dir():
        raise ValueError("runtime root must be a canonical absolute directory")
    digest = hashlib.sha256()
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat = path.lstat()
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not allow_system_links or not (
                root in target.parents
                or (
                    not target.is_dir()
                    and any(
                        parent in target.parents
                        for parent in (Path("/usr"), Path("/lib"), Path("/lib64"))
                    )
                )
            ):
                raise ValueError("unsupported runtime symlink: " + relative)
            digest.update(json.dumps([relative, "link", os.readlink(path)]).encode())
        elif path.is_dir():
            digest.update(json.dumps([relative, "directory", stat.st_mode & 0o777]).encode())
        elif path.is_file():
            total += stat.st_size
            if total > 4 * 1024**3:
                raise ValueError("runtime tree exceeds four GiB bound")
            digest.update(
                json.dumps([relative, "file", stat.st_mode & 0o777, stat.st_size]).encode()
            )
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
        else:
            raise ValueError("runtime tree contains a nonregular file: " + relative)
    return digest.hexdigest()


def _stop_recorded_command(path: Path) -> None:
    """Fallback after broker termination, guarded by child PID/start identity."""
    if not path.exists():
        return
    identity = json.loads(path.read_text())
    pid = identity["pid"]
    process = Path("/proc") / str(pid)
    try:
        fields = (process / "stat").read_text().rsplit(")", 1)[1].split()
        if (
            process.stat().st_uid != os.getuid()
            or int(fields[19]) != identity["start"]
            or int(fields[2]) != pid
        ):
            raise RuntimeUnavailable("owned host command identity changed")
        os.killpg(pid, signal.SIGKILL)
    except FileNotFoundError:
        pass
    except ProcessLookupError:
        pass


class HostSession:
    """Trusted raw broker. Never hand this object to a model environment."""

    def __init__(self, root: Path, repo: Path, pin: HostRuntimePin) -> None:
        self.root, self.repo, self.pin = root, repo, pin
        self.closed = False
        self.monitor = None
        self.command_identity = root / "broker-owned-command.json"
        broker = root / "broker.py"
        source = Path(__file__).with_name("pyxis_worker.py").read_text()
        source = source.replace(
            'if __name__ == "__main__":',
            "def _terminate(signum, frame):\n    raise SystemExit(143)\n\n"
            'signal.signal(signal.SIGTERM, _terminate)\n\nif __name__ == "__main__":',
        )
        identity_path = repr(str(self.command_identity))
        source = source.replace(
            '    output = {"stdout": bytearray(), "stderr": bytearray()}',
            "    Path(" + identity_path + ').write_text(json.dumps({"pid":process.pid, '
            '"start":int(Path("/proc/"+str(process.pid)+"/stat").read_text()'
            '.rsplit(")",1)[1].split()[19])}))\n'
            '    output = {"stdout": bytearray(), "stderr": bytearray()}',
        )
        source = source.replace(
            "        process.stderr.close()",
            "        process.stderr.close()\n        Path("
            + identity_path
            + ").unlink(missing_ok=True)",
        )
        broker.write_text(source)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(root), "LANG": "C.UTF-8"}
        self.process = subprocess.Popen(
            [str(pin.system_python), "-I", "-B", str(broker)],
            cwd=root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        ready = self._receive(10)
        if ready.get("ready") is not True:
            self.stop()
            raise RuntimeUnavailable("host broker did not become ready")
        from domains.swe_agents.environment.host_tree_monitor import HostTreeMonitor

        self.monitor = HostTreeMonitor(root, self.process)

    def _receive(self, timeout: float) -> dict[str, Any]:
        assert self.process.stdout is not None
        deadline = time.monotonic() + timeout
        data = bytearray()
        while True:
            if self.monitor is not None and self.monitor.reason:
                raise RuntimeUnavailable(self.monitor.reason)
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise RuntimeUnavailable("host broker deadline expired")
            byte = os.read(self.process.stdout.fileno(), 65536)
            if not byte:
                raise RuntimeUnavailable("host broker exited")
            data.extend(byte)
            if len(data) > 9_000_000:
                raise RuntimeUnavailable("host broker response exceeds bound")
            if data.endswith(b"\n"):
                return json.loads(data)

    def exec(self, command: str, timeout: float = 60) -> tuple[int, str, str]:
        if self.closed or not 0 < timeout <= 900 or len(command.encode()) > 1_000_000:
            raise RuntimeUnavailable("invalid host broker request")
        # Only trusted preparation reaches raw exec; model calls require host guard.
        prefix = "export PATH=" + shlex.quote(str(self.pin.venv / "bin") + ":/usr/bin:/bin")
        request = {
            "command": prefix + "; cd -- " + shlex.quote(str(self.repo)) + " && " + command,
            "timeout": timeout,
        }
        assert self.process.stdin is not None
        try:
            self.process.stdin.write((json.dumps(request) + "\n").encode())
            self.process.stdin.flush()
            result = self._receive(timeout + 5)
        except Exception:
            self.stop()
            raise
        if "error" in result:
            raise RuntimeUnavailable(result["error"])
        return result["exit"], result["stdout"], result["stderr"]

    def read_file(self, path: str) -> str:
        target = Path(path)
        target = target if target.is_absolute() else self.repo / target
        if self.repo not in target.resolve().parents or target.stat().st_size > 4_000_000:
            raise RuntimeUnavailable("invalid raw host read")
        return target.read_text()

    def write_file(self, path: str, content: str) -> None:
        target = Path(path)
        target = target if target.is_absolute() else self.repo / target
        if (
            self.root not in target.parent.resolve().parents
            and target.parent.resolve() != self.root
        ):
            raise RuntimeUnavailable("raw writes must remain in the private session root")
        if len(content.encode()) > 4_000_000 or target.is_symlink():
            raise RuntimeUnavailable("invalid raw host write")
        target.write_text(content)

    def checkpoint(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        raise RuntimeUnavailable("host runtime does not provide trusted candidate snapshots")

    def stop(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            # This Popen is an unreaped owned child, so its PID cannot have been reused.
            os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()
        if self.monitor is not None:
            self.monitor.stop()
        _stop_recorded_command(self.command_identity)
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe is not None:
                pipe.close()
        shutil.rmtree(self.root)


class InteractiveRuntime:
    def __init__(self, pin: HostRuntimePin, *, parent: Path = Path("/tmp")) -> None:
        self.pin, self.parent = pin, parent

    def verify(self) -> None:
        if sys.platform != "linux":
            raise RuntimeUnavailable("interactive host runtime requires Linux")
        if self.pin.kind != "interactive_host_runtime_v1":
            raise RuntimeUnavailable("a separately registered host runtime pin is required")
        if (
            self.pin.system_python.resolve() != self.pin.system_python
            or Path("/usr") not in self.pin.system_python.parents
        ):
            raise RuntimeUnavailable("guard startup requires a pinned canonical system interpreter")
        if tree_digest(self.pin.repository) != self.pin.repository_sha256:
            raise RuntimeUnavailable("pristine host repository digest differs")
        if tree_digest(self.pin.venv, allow_system_links=True) != self.pin.venv_sha256:
            raise RuntimeUnavailable("frozen host venv digest differs")
        require_clean_prepared_tree(self.pin.repository)

    def start_guarded(
        self, boundary_factory: Callable[[HostSession, HostRuntimePin], Session] | None = None
    ) -> Session:
        if boundary_factory is None:
            raise RuntimeUnavailable(
                "reviewed host filesystem and aggregate resource boundary required"
            )
        self.verify()
        root = Path(tempfile.mkdtemp(prefix="prun-interactive-", dir=self.parent)).resolve()
        repo = root / "repo"
        shutil.copytree(self.pin.repository, repo, symlinks=False)
        if tree_digest(repo) != self.pin.repository_sha256:
            shutil.rmtree(root)
            raise RuntimeUnavailable("copied repository digest differs")
        raw = HostSession(root, repo, self.pin)
        try:
            guarded = boundary_factory(raw, self.pin)
            if guarded is raw:
                raise RuntimeUnavailable("raw host session cannot be the target boundary")
            guarded.require_boundary()
            return guarded
        except Exception:
            raw.stop()
            raise


def require_clean_prepared_tree(repository: Path) -> None:
    """A source artifact must start with no tracked changes against prepared HEAD."""
    with tempfile.TemporaryDirectory(prefix="prun-prepared-index-") as directory:
        index = Path(directory) / "index"
        shutil.copyfile(repository / ".git/index", index)
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-c",
                "core.fileMode=true",
                "diff",
                "--exit-code",
                "--no-ext-diff",
                "--no-textconv",
                "HEAD",
                "--",
            ],
            cwd=repository,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_INDEX_FILE": str(index),
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True,
        )
    if result.returncode:
        raise RuntimeUnavailable("prepared host tree differs from its Git checkpoint")
