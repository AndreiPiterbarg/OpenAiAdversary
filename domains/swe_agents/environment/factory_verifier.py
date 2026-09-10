"""Narrow external assertions for one pinned Factory Boy task.

This is a source-observation adapter, not a generic pytest oracle or image-admission
implementation. The caller must capture the complete package from verified fresh state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

KEY = "factoryboy__factory_boy-1067"
COMMIT = "7ed1e5417e06c3d83e0495a67508b3868de53823"
IMAGE_SHA256 = "952718fc40ab69f169607ee8216615f8c208f7413ebbcda29e3900858fab53c7"
RECEIPT = "3a688c64f85d29d2ac6ea4217899f03ab0c9eac083c30d1f3a2ba81f5c5737ca"
F2P = ("tests/test_regression.py::FakerRegressionTests::test_evaluated_without_locale",)
P2P = ("tests/test_regression.py::FakerRegressionTests::test_locale_issue",)


class FactoryVerifierUnavailable(RuntimeError):
    """No protected observation available; never interpreted as a task failure."""


def evaluate_observations(value: Any) -> dict[str, bool]:
    """Evaluate primitive candidate observations in the trusted parent only."""
    keys = {"f2p_pseudonym", "p2p_pseudonym", "p2p_unknown_fullname"}
    if type(value) is not dict or set(value) != keys:
        raise FactoryVerifierUnavailable("invalid observation schema")
    if not (
        type(value["f2p_pseudonym"]) is str
        and (value["p2p_pseudonym"] is None or type(value["p2p_pseudonym"]) is str)
        and type(value["p2p_unknown_fullname"]) is str
    ):
        raise FactoryVerifierUnavailable("invalid observation types")
    return {
        "maybe_output_in_declared_choices": value["f2p_pseudonym"] in ("yes", "no"),
        "locale_outputs_match_contract": (
            value["p2p_unknown_fullname"] == "" and value["p2p_pseudonym"] is None
        ),
    }


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in items:
        if key in value:
            raise FactoryVerifierUnavailable("duplicate JSON key")
        value[key] = item
    return value


class FactoryFinalVerifier:
    def __init__(
        self,
        pin: dict[str, Any],
        *,
        python_executable: str = sys.executable,
        worker_path: str | Path | None = None,
        confinement_path: str | Path | None = None,
    ) -> None:
        expected = {
            "key": KEY,
            "commit": COMMIT,
            "image_sha256": IMAGE_SHA256,
            "verification_receipt": RECEIPT,
        }
        if any(pin.get(k) != v for k, v in expected.items()):
            raise ValueError("unsupported or unbound Factory Boy pin")
        if tuple(pin.get("fail_to_pass", ())) != F2P or tuple(pin.get("pass_to_pass", ())) != P2P:
            raise ValueError("Factory Boy test identifiers differ")
        self.python = str(python_executable)
        self.worker = Path(worker_path or Path(__file__).with_name("factory_worker.py")).resolve()
        self.confinement = Path(
            confinement_path or Path(__file__).parents[3] / "adversary/execution/confinement.py"
        ).resolve()

    def require_protected(self) -> None:
        raise FactoryVerifierUnavailable(
            "source adapter requires image capture and live confinement per evaluation; "
            "it is not a generic protected FinalOracle"
        )

    def evaluate_sources(
        self,
        sources: dict[str, str],
        *,
        changed_paths: tuple[str, ...] = ("factory/declarations.py",),
        timeout: float = 15,
    ) -> dict[str, Any]:
        if not set(changed_paths) <= {"factory/declarations.py"}:
            raise ValueError("unsupported candidate patch path")
        if not isinstance(timeout, (float, int)) or not 0 < timeout <= 60:
            raise ValueError("invalid observation timeout")
        if type(sources) is not dict or "factory/__init__.py" not in sources:
            raise ValueError("complete captured factory package required")
        for path, source in sources.items():
            if (
                type(path) is not str
                or not re.fullmatch(r"factory/(?:[A-Za-z_]\w*/)*[A-Za-z_]\w*\.py", path)
                or type(source) is not str
            ):
                raise ValueError("invalid captured package source")
        request = json.dumps({"sources": sources}, sort_keys=True).encode()
        if len(request) > 2_000_000:
            raise ValueError("source request exceeds byte bound")
        read_fd, write_fd = os.pipe()
        process = None
        output = {"stdout": bytearray(), "stderr": bytearray(), "capability": bytearray()}
        try:
            process = subprocess.Popen(
                [self.python, "-I", "-B", str(self.worker), str(write_fd), str(self.confinement)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(write_fd,),
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                cwd="/",
                start_new_session=True,
            )
            os.close(write_fd)
            write_fd = -1
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                for file, label in (
                    (process.stdout, "stdout"),
                    (process.stderr, "stderr"),
                    (read_fd, "capability"),
                ):
                    selector.register(file, selectors.EVENT_READ, label)
                sent = 0
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        raise FactoryVerifierUnavailable("observation timed out")
                    for key, _ in selector.select(0.1):
                        if key.data == "stdin":
                            try:
                                sent += os.write(key.fd, request[sent : sent + 65536])
                            except BrokenPipeError:
                                sent = len(request)
                            if sent == len(request):
                                selector.unregister(key.fileobj)
                                process.stdin.close()
                            continue
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output[key.data].extend(chunk)
                        if len(output[key.data]) > 65536:
                            raise FactoryVerifierUnavailable("observation output exceeds bound")
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
            if bytes(output["capability"]) != b"factory-seccomp-v1\n":
                raise FactoryVerifierUnavailable("confinement capability unavailable")
            if process.returncode:
                raise FactoryVerifierUnavailable(
                    "candidate produced no complete observation: "
                    + output["stderr"][-1000:].decode(errors="replace")
                )
            try:
                observations = json.loads(output["stdout"], object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError) as exc:
                raise FactoryVerifierUnavailable("invalid candidate observation JSON") from exc
            statuses = evaluate_observations(observations)
            return {
                "kind": "factory_source_observation_v1",
                "task_key": KEY,
                "interface_assertions": statuses,
                "interface_success": all(statuses.values()),
                "original_test_verdict": None,
                "authenticated_test_evidence": False,
                "scope": "bounded process-output contract; candidate may forge its observations",
                "observations": observations,
                "source_sha256": hashlib.sha256(request).hexdigest(),
                "worker_sha256": hashlib.sha256(self.worker.read_bytes()).hexdigest(),
                "confinement_sha256": hashlib.sha256(self.confinement.read_bytes()).hexdigest(),
            }
        finally:
            if write_fd >= 0:
                os.close(write_fd)
            os.close(read_fd)
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()


DECLARATIONS_SHA256 = "a850dc32d4ddc733172da6c74f8c865429fa858072d017cdbeaeb4759c428672"
_REPAIR_LINE = "        choice = self.decider.evaluate(instance=instance, step=step, extra={})\n"


def admit_restricted_sources(
    pristine_sources: dict[str, str], candidate_sources: dict[str, str]
) -> dict[str, Any]:
    """Admit exactly a four-element repair grammar, never arbitrary Python.

    The caller supplies the complete package captured from the verified pristine image.
    This checks every captured byte and pins the edited file independently. It does not
    authenticate an arbitrary caller's other files, image, environment or test process.
    """
    path = "factory/declarations.py"
    if type(pristine_sources) is not dict or type(candidate_sources) is not dict:
        raise ValueError("source mappings required")
    if set(pristine_sources) != set(candidate_sources) or path not in pristine_sources:
        raise ValueError("restricted repair must preserve complete source closure")
    if any(type(k) is not str or type(v) is not str for k, v in pristine_sources.items()):
        raise ValueError("pristine source mapping must contain text")
    if any(type(v) is not str for v in candidate_sources.values()):
        raise ValueError("candidate source mapping must contain text")
    base = pristine_sources[path]
    if hashlib.sha256(base.encode()).hexdigest() != DECLARATIONS_SHA256:
        raise ValueError("pristine declarations differs from frozen source")
    if base.count(_REPAIR_LINE) != 1:
        raise ValueError("frozen repair site is not unique")
    for name in pristine_sources:
        if name != path and pristine_sources[name] != candidate_sources[name]:
            raise ValueError("candidate changes source outside restricted repair site")
    for method in ("evaluate", "evaluate_pre"):
        for keyword in ("extra", "overrides"):
            line = (
                f"        choice = self.decider.{method}"
                f"(instance=instance, step=step, {keyword}={{}})\n"
            )
            if candidate_sources[path] == base.replace(_REPAIR_LINE, line, 1):
                payload = json.dumps(candidate_sources, sort_keys=True).encode()
                return {
                    "kind": "factory_finite_repair_grammar_v1",
                    "task_key": KEY,
                    "method": method,
                    "keyword": keyword,
                    "candidate_sources_sha256": hashlib.sha256(payload).hexdigest(),
                    "pristine_declarations_sha256": DECLARATIONS_SHA256,
                    "arbitrary_python_admitted": False,
                }
    raise ValueError("candidate is outside the four-element restricted repair grammar")
