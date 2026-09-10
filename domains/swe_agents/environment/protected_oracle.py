"""Fresh candidate replay, with an explicit boundary before protected verification.

A fresh image prevents persistence of target edits outside the exported patch. It does
not protect a same-user test process, its output pipe, or the broker from candidate code.
Consequently this instrument supplies diagnostics, never protected final verdicts.
"""

import hashlib
import json
import re
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from adversary.domain.channel import relative_path
from domains.swe_agents.environment.gold import digest
from domains.swe_agents.environment.readset import MANIFESTS
from domains.swe_agents.environment.runtime import ContainerRuntime, RuntimeUnavailable, Session
from domains.swe_agents.environment.spec import SweOracle, TaskPin


class CandidatePatchRejected(ValueError):
    """Candidate transport or patch violates the replay contract; not a test failure."""


class FinalOracle(Protocol):
    """Trusted application boundary, not a model-supplied declaration of protection."""

    def require_protected(self) -> None:
        """Refuse unless the implementation enforces protected final verification."""

    def evaluate(self, source_session: Session) -> dict[str, Any]: ...


class FreshReplayOracle:
    """Replay only a supplied diff in fresh pinned state, without claiming isolation.

    The explicit exporter must produce a diff against the prepared task baseline, including
    new files. Ordinary ``git diff HEAD`` is insufficient when a test patch was installed.
    No target snapshot is imported as verifier evidence. Environment/package changes outside
    the diff are intentionally not reproduced, so this is not the full dual oracle.
    """

    def __init__(
        self,
        runtime: ContainerRuntime,
        pin: TaskPin,
        oracle: SweOracle,
        *,
        export_patch: Callable[[Session], str] | None = None,
        max_patch_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if pin.image is None or pin.image_sha256 is None:
            raise ValueError("fresh replay requires an image and its frozen digest")
        if (
            oracle.test_command != pin.test_command
            or oracle.fail_to_pass != pin.fail_to_pass
            or oracle.pass_to_pass != pin.pass_to_pass
        ):
            raise ValueError("final oracle differs from the trusted task pin")
        if type(max_patch_bytes) is not int or max_patch_bytes <= 0:
            raise ValueError("patch byte bound must be a positive integer")
        self.runtime, self.pin, self.oracle = runtime, pin, oracle
        self.export_patch, self.max_patch_bytes = export_patch, max_patch_bytes

    def require_protected(self) -> None:
        raise RuntimeUnavailable(
            "fresh replay is not a protected oracle: candidate code shares test identity and "
            "output channel; runtime does not enforce a separate verifier process, immutable "
            "verifier inputs, denied network/credentials, or authenticated test evidence"
        )

    def evaluate(self, source_session: Session) -> dict[str, Any]:
        if self.export_patch is None:
            raise RuntimeUnavailable("fresh replay requires a prepared-baseline patch exporter")
        return self.evaluate_patch(self.export_patch(source_session), source_session=source_session)

    def _protected(self, path: str) -> bool:
        roots = (*self.pin.protected_paths, *self.oracle.protected_paths)
        tests = (*self.oracle.fail_to_pass, *self.oracle.pass_to_pass)
        protected = tuple(relative_path(p.rstrip("/")) for p in roots)
        test_files = tuple(relative_path(node.split("::", 1)[0]) for node in tests)
        name = Path(path).name
        return (
            ".git" in Path(path).parts
            or name == "conftest.py"
            or name in MANIFESTS
            or name.endswith(".lock")
            or name.startswith("requirements") and name.endswith((".txt", ".in"))
            or any(path == p or path.startswith(p + "/") for p in (*protected, *test_files))
        )

    @staticmethod
    def _regular_paths(session: Session, paths: list[str]) -> None:
        """Inspect paths without importing candidate modules or following symbolic links.

        This check runs before candidate code. It protects the replay input boundary;
        it does not prevent a subsequently imported candidate from modifying tests.
        """
        checks = []
        for path in paths:
            parts = path.split("/")
            for n in range(1, len(parts) + 1):
                quoted = shlex.quote("./" + "/".join(parts[:n]))
                flag = "-f" if n == len(parts) else "-d"
                checks.append(
                    f"if [ -L {quoted} ] || {{ [ -e {quoted} ] && ! [ {flag} {quoted} ]; }}; "
                    "then exit 3; fi"
                )
        command = "; ".join((*checks, "exit 0"))
        code, _, err = session.exec(command, 60)
        if code == 3:
            raise CandidatePatchRejected("candidate paths must be regular files without links")
        if code:
            raise RuntimeUnavailable("cannot inspect candidate path types: " + err[-1000:])

    @staticmethod
    def _checked(session: Session, command: str, timeout: float = 60) -> str:
        code, out, err = session.exec(command, timeout)
        if code:
            raise RuntimeUnavailable("fresh replay setup failed: " + err[-1000:])
        return out

    def evaluate_patch(
        self, patch: str, *, source_session: Session | None = None
    ) -> dict[str, Any]:
        if not isinstance(patch, str) or "\x00" in patch:
            raise CandidatePatchRejected("candidate patch must be NUL-free text")
        try:
            patch_bytes = patch.encode("utf-8")
        except UnicodeError as exc:
            raise CandidatePatchRejected("candidate patch must be valid UTF-8 text") from exc
        if len(patch_bytes) > self.max_patch_bytes:
            raise CandidatePatchRejected("candidate patch exceeds byte bound")
        if digest(Path(self.pin.image)) != self.pin.image_sha256:
            raise RuntimeUnavailable("fresh replay image differs from its frozen digest")
        session = self.runtime.start(
            self.pin.image,
            self.pin.url,
            self.pin.commit,
            workdir=self.pin.workdir,
            python_env=self.pin.python_env,
        )
        if session is source_session:
            # The caller still owns the target; a faulty runtime must not close it here.
            raise RuntimeUnavailable("final verification requires a distinct fresh session")
        try:
            path = self._checked(session, "mktemp /tmp/pcode-oracle-XXXXXXXX").strip()
            if not re.fullmatch(r"/tmp/pcode-oracle-[A-Za-z0-9]+", path):
                raise RuntimeUnavailable("fresh replay returned an invalid temporary path")
            quoted = shlex.quote(path)
            if self.pin.test_patch:
                session.write_file(path, self.pin.test_patch)
                self._checked(session, "git apply --check -- " + quoted)
                self._checked(session, "git apply -- " + quoted)
            session.checkpoint()
            # Collect package facts before candidate files can shadow collector imports.
            # These describe the replay environment, never the target's package state.
            snapshot = dict(session.snapshot())
            touched: list[str] = []
            if patch:
                # --numstat from git apply can report only a rename destination.
                # Refuse rename/copy transport rather than omit a protected source path.
                if re.search(r"^(?:rename|copy) (?:from|to) ", patch, re.MULTILINE):
                    raise CandidatePatchRejected("candidate rename/copy patches are unsupported")
                # Git accepts symlinks and gitlinks as valid patches. Neither is a
                # supported candidate transport: both can redirect verifier reads.
                for mode in re.findall(
                    r"^(?:old mode|new mode|new file mode|deleted file mode) (\S+)$",
                    patch, re.MULTILINE,
                ):
                    if mode not in ("100644", "100755"):
                        raise CandidatePatchRejected(
                            "candidate patch contains unsupported file mode"
                        )
                session.write_file(path, patch)
                code, out, _ = session.exec("git apply --numstat -z -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate is not a valid patch")
                for record in out.split("\x00"):
                    if not record:
                        continue
                    fields = record.split("\t", 2)
                    if len(fields) != 3:
                        raise CandidatePatchRejected("ambiguous candidate patch paths")
                    try:
                        item = relative_path(fields[2])
                    except ValueError as exc:
                        raise CandidatePatchRejected("unsafe candidate patch path") from exc
                    if self._protected(item):
                        raise CandidatePatchRejected("candidate changes verifier input: " + item)
                    touched.append(item)
                if not touched:
                    raise CandidatePatchRejected("nonempty candidate patch has no file changes")
                self._regular_paths(session, touched)
                code, _, _ = session.exec("git apply --check -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate patch does not apply to prepared task")
                self._checked(session, "git apply -- " + quoted)
                self._regular_paths(session, touched)
            self._checked(session, "rm -- " + quoted)
            # Candidate transport was parsed in fresh state before any candidate code ran.
            # Session implementations may omit paths or include the installed test patch.
            snapshot["changed_files"] = sorted(set(touched))
            code, out, err = session.exec(self.oracle.test_command, 900)
            snapshot["test_results"] = {"exit": code, "stdout": out, "stderr": err}
            snapshot["oracle_replay"] = {
                "kind": "fresh_replay_unisolated",
                "image_sha256": self.pin.image_sha256,
                "pin_sha256": hashlib.sha256(
                    json.dumps(self.pin.model_dump(mode="json"), sort_keys=True).encode()
                ).hexdigest(),
                "oracle_sha256": hashlib.sha256(
                    json.dumps(self.oracle.model_dump(mode="json"), sort_keys=True).encode()
                ).hexdigest(),
                "candidate_sha256": hashlib.sha256(patch_bytes).hexdigest(),
                "changed_paths": sorted(set(touched)),
                "limitations": [
                    "same-user candidate code can tamper with tests and their output at runtime",
                    "target package and environment changes are not replayed",
                    "static protected paths are not a complete oracle read set",
                ],
            }
            return snapshot
        finally:
            session.stop()
