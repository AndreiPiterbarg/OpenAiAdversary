"""Fresh enroot sessions on a dev worker; no shared mutable task images.

Enroot is a task runtime, not a security boundary for model-authored Python. Observation
programs require a separate confined executor; this runtime does not claim to provide it.
"""

import base64
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from domains.swe_agents.environment.runtime import RuntimeUnavailable


class EnrootRuntime:
    """Extract each immutable image into a private, disposable session directory."""

    def __init__(
        self,
        scratch: str | Path,
        *,
        executable: str = "enroot",
        namespace_helper: str = "enroot-nsenter",
    ) -> None:
        self.scratch = Path(scratch).resolve()
        self.executable = executable
        self.namespace_helper = namespace_helper

    def start(
        self,
        image: str | None,
        url: str,
        commit: str,
        *,
        workdir: str | None = None,
        python_env: str = "image",
    ) -> "EnrootSession":
        if python_env != "image":
            raise RuntimeUnavailable("use Pyxis for the verified Conda environment")
        if workdir is not None and not re.fullmatch(r"/[A-Za-z0-9_.-]+", workdir):
            raise ValueError("invalid task workdir")
        if not image or not Path(image).is_file():
            raise RuntimeUnavailable("an existing pinned squashfs image is required")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("commit must be an immutable full revision")
        name = Path(urlparse(url).path).name.removesuffix(".git")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
            raise ValueError("cannot derive a safe repository path from the URL")
        self.scratch.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="pcode-episode-", dir=self.scratch))
        session = EnrootSession(directory, workdir or f"/{name}", self.executable)
        try:
            # Refuse before costly extraction when the host denies the basic namespace.
            # Passing this probe is necessary, not sufficient for full image startup.
            session._command(
                [self.namespace_helper, "--user", "--mount", "/bin/true"],
                timeout=30,
                check=True,
            )
            session._command(
                [self.executable, "create", "--name", "task", str(Path(image).resolve())],
                timeout=600,
                check=True,
            )
            session._checked(f"git checkout --detach {shlex.quote(commit)}", 120)
            actual = session._checked("git rev-parse HEAD", 30).strip()
            if actual != commit:
                raise RuntimeUnavailable("image did not check out the pinned revision")
            # No reset of a cached/shared image: only this newly extracted session is changed.
            if session._checked("git status --porcelain --untracked-files=no", 30).strip():
                raise RuntimeUnavailable("pinned checkout contains tracked modifications")
            session._baseline = session._files()
            session._packages = session._installed()
            return session
        except BaseException:
            session.stop()
            raise


class EnrootSession:
    """Each command re-enters the same private filesystem; processes have finite lifetimes."""

    def __init__(self, directory: Path, workdir: str, executable: str) -> None:
        self.directory, self.workdir, self.executable = directory, workdir, executable
        self.closed = False
        self._baseline: dict[str, str] = {}
        self._packages: dict[str, str] = {}
        # The credential-bearing host environment never enters a task subprocess.
        self.env = {
            k: os.environ[k] for k in ("PATH", "HOME", "USER", "LOGNAME", "LANG") if k in os.environ
        }
        self.env.update(
            {
                "ENROOT_DATA_PATH": str(directory / "data"),
                "ENROOT_RUNTIME_PATH": str(directory / "run"),
                "ENROOT_CONFIG_PATH": str(directory / "config"),
                "ENROOT_MOUNT_HOME": "no",
                "ENROOT_LOGIN_SHELL": "no",
            }
        )
        for name in ("data", "run", "config", "cache", "temp"):
            (directory / name).mkdir()
        self.env["ENROOT_CACHE_PATH"] = str(directory / "cache")
        self.env["ENROOT_TEMP_PATH"] = str(directory / "temp")
        self.rc = directory / "rc.sh"
        self.rc.write_text('#!/bin/sh\nexec "$@"\n')

    def _command(
        self, argv: list[str], timeout: float, *, check: bool = False
    ) -> tuple[int, str, str]:
        if self.closed:
            raise RuntimeError("session is closed")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env=self.env,
                start_new_session=True,
            )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeUnavailable("runtime command timed out") from exc
            # Background descendants must not mutate the filesystem after a command returns.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout.seek(0)
            stderr.seek(0)
            out, err = stdout.read(8_000_001), stderr.read(8_000_001)
            if len(out) > 8_000_000 or len(err) > 8_000_000:
                raise RuntimeUnavailable("runtime output exceeded the audit limit")
        result = process.returncode, out.decode(errors="replace"), err.decode(errors="replace")
        if check and result[0]:
            raise RuntimeUnavailable(f"runtime command failed ({result[0]}): {result[2][-1000:]}")
        return result

    def exec(self, command: str, timeout: float) -> tuple[int, str, str]:
        # Bypass image startup scripts; never interpolate a model command into the host shell.
        wrapped = f"cd -- {shlex.quote(self.workdir)} && exec /bin/bash -c {shlex.quote(command)}"
        return self._command(
            [
                self.executable,
                "start",
                "--root",
                "--rw",
                "--rc",
                str(self.rc),
                "task",
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-c",
                wrapped,
            ],
            timeout,
        )

    def _checked(self, command: str, timeout: float) -> str:
        code, out, err = self.exec(command, timeout)
        if code:
            raise RuntimeUnavailable(f"task command failed ({code}): {err[-1000:]}")
        return out

    def read_file(self, path: str) -> str:
        return self._checked(f"cat -- {shlex.quote(path)}", 30)

    def write_file(self, path: str, content: str) -> None:
        payload = base64.b64encode(content.encode()).decode()
        self._checked(f"printf %s {shlex.quote(payload)} | base64 -d > {shlex.quote(path)}", 30)

    def _files(self) -> dict[str, str]:
        # Hash actual contents, not git status: an agent can rewrite the index or commit.
        script = """import hashlib,json,os,stat
files={}
for parent,dirs,names in os.walk('.'):
    dirs[:]=sorted(d for d in dirs if d != '.git')
    for name in sorted(names + [d for d in dirs if os.path.islink(os.path.join(parent,d))]):
        path=os.path.join(parent,name)
        mode=os.lstat(path).st_mode
        if stat.S_ISLNK(mode): value='link:'+os.readlink(path)
        elif stat.S_ISREG(mode):
            digest=hashlib.sha256()
            with open(path,'rb') as handle:
                for chunk in iter(lambda:handle.read(1048576),b''): digest.update(chunk)
            value=str(stat.S_IMODE(mode))+':'+digest.hexdigest()
        else: value='special:'+str(mode)
        files[path[2:]]=value
print(json.dumps(files,sort_keys=True))"""
        return json.loads(self._checked(f"python -c {shlex.quote(script)}", 180))

    def _installed(self) -> dict[str, str]:
        script = (
            "import importlib.metadata as m,json; "
            "print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version "
            "for d in m.distributions()}))"
        )
        return json.loads(self._checked(f"python -c {shlex.quote(script)}", 60))

    def checkpoint(self) -> None:
        """Record the prepared baseline before the target can alter task files."""
        self._baseline = self._files()
        self._packages = self._installed()

    def snapshot(self) -> dict[str, Any]:
        files, packages = self._files(), self._installed()
        return {
            "changed_files": sorted(
                p
                for p in files.keys() | self._baseline.keys()
                if files.get(p) != self._baseline.get(p)
            ),
            "installed_packages": packages,
            "added_packages": sorted(packages.keys() - self._packages.keys()),
        }

    def stop(self) -> None:
        if not self.closed:
            self.closed = True
            shutil.rmtree(self.directory)
