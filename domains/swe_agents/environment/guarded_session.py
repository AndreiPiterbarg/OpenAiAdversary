"""Route target tools through an installed, inherited kernel guard.

Trusted preparation uses the private raw session before this wrapper is exposed.
Only the wrapper is handed to the target environment; its source artifact remains
untrusted and is admitted independently in fresh verification state.
"""

from __future__ import annotations

import hashlib
import json
import math
import posixpath
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session


def _readonly_interpreter(path: str) -> str:
    if (
        type(path) is not str
        or posixpath.normpath(path) != path
        or not any(
            root in PurePosixPath(path).parents
            for root in (PurePosixPath("/usr"), PurePosixPath("/opt"))
        )
    ):
        raise RuntimeUnavailable("guard interpreter must be an absolute readonly /usr or /opt path")
    return path


class GuardedSession:
    def __init__(
        self,
        raw: Session,
        repo: str,
        scratch: str,
        guard: str,
        guard_source: bytes,
        command_timeout: float = 60,
        *,
        python_executable: str = "/usr/bin/python3",
    ) -> None:
        self._raw, self.repo, self.scratch, self.guard = raw, repo, scratch, guard
        if not 0 < command_timeout <= 900:
            raise ValueError("guard timeout must be in (0, 900]")
        self.command_timeout = command_timeout
        self.python_executable = _readonly_interpreter(python_executable)
        self.guard_sha256 = hashlib.sha256(guard_source).hexdigest()
        self.attestation: dict[str, Any] | None = None

    def exec(self, command: str, timeout: float = 60) -> tuple[int, str, str]:
        effective_timeout = min(timeout, self.command_timeout)
        if not math.isfinite(effective_timeout) or effective_timeout <= 0:
            raise ValueError("command timeout must be finite and positive")
        argv = [
            self.python_executable,
            "-I",
            self.guard,
            "--repo",
            self.repo,
            "--scratch",
            self.scratch,
            "--cpu-seconds",
            str(math.ceil(effective_timeout)),
            "--",
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            command,
        ]
        return self._raw.exec(shlex.join(argv), effective_timeout)

    def read_file(self, path: str) -> str:
        code, out, err = self.exec("cat -- " + shlex.quote(path), 30)
        if code:
            raise RuntimeUnavailable("guarded read failed: " + err[-500:])
        return out

    def preflight(self) -> None:
        # Called in trusted pristine state, before any model-authored command.
        probe = """import errno,json,os,socket
checks={}
for path in ['/proc/self/status','/proc/1/mem']:
 try:
  open(path).close(); checks[path]=False
 except PermissionError: checks[path]=True
 except FileNotFoundError: checks[path]=False
actions=[('network',lambda:socket.socket()),('signal',lambda:os.kill(os.getppid(),0)),
 ('system_write',lambda:os.close(os.open('/etc/passwd',os.O_WRONLY)))]
for name,action in actions:
 try: action(); checks[name]=False
 except PermissionError: checks[name]=True
p='.prun_guard_probe_'+str(os.getpid())
with open(p,'w') as f:f.write('ok')
os.unlink(p)
print(json.dumps(checks,sort_keys=True))
assert all(checks.values())
"""
        code, out, err = self.exec("python -I -c " + shlex.quote(probe), 30)
        if code:
            raise RuntimeUnavailable("target guard preflight failed: " + err[-1000:])
        checks = json.loads(out)
        if len(checks) != 5 or not all(value is True for value in checks.values()):
            raise RuntimeUnavailable("target guard did not establish denied capabilities")
        self.attestation = {
            "guard_sha256": self.guard_sha256,
            "python_executable": self.python_executable,
            "checks": checks,
            "scope": "all target tool commands use inherited kernel guard",
        }

    def require_boundary(self) -> None:
        if self.attestation is None:
            raise RuntimeUnavailable("target guard has not passed live preflight")

    def stop(self) -> None:
        self._raw.stop()


def install_guard(raw: Session, repo: str, *, command_timeout: float = 60) -> GuardedSession:
    # Bind before applying any candidate bytes. Keep the image's venv executable
    # path (and its package environment), but verify its real target is readonly too.
    probe = (
        "import json,pathlib,sys; print(json.dumps({'executable':sys.executable,"
        "'resolved':str(pathlib.Path(sys.executable).resolve(strict=True))}))"
    )
    code, output, error = raw.exec("python -I -c " + shlex.quote(probe), 30)
    if code:
        raise RuntimeUnavailable("cannot bind pristine guard interpreter: " + error[-500:])
    try:
        interpreter = json.loads(output)
        executable = _readonly_interpreter(interpreter["executable"])
        _readonly_interpreter(interpreter["resolved"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeUnavailable("invalid pristine guard interpreter evidence") from exc
    source = Path(__file__).with_name("target_guard.py").read_bytes()
    code, root, err = raw.exec("mktemp -d /tmp/prun-guard-XXXXXXXX", 30)
    if code:
        raise RuntimeUnavailable("guard preparation failed: " + err[-500:])
    root = root.strip()
    if not root.startswith("/tmp/prun-guard-") or "/" in root[len("/tmp/") :]:
        raise RuntimeUnavailable("invalid private guard directory")
    raw.write_file(root + "/guard.py", source.decode())
    code, _, err = raw.exec("mkdir " + shlex.quote(root + "/scratch"), 30)
    if code:
        raise RuntimeUnavailable("guard scratch preparation failed: " + err[-500:])
    result = GuardedSession(
        raw,
        repo,
        root + "/scratch",
        root + "/guard.py",
        source,
        command_timeout=command_timeout,
        python_executable=executable,
    )
    result.preflight()
    return result
