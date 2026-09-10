"""Frozen-image control/candidate runner for the finite Factory Boy repair grammar.

Invoke only in a fresh image whose bytes were checked by the allocation controller.
No candidate checkout, shell command, environment, or arbitrary patch is accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("baseline", "gold", "candidate"))
    parser.add_argument("--input", type=Path, default=Path("/va-input"))
    parser.add_argument("--output", type=Path, default=Path("/va-output"))
    args = parser.parse_args()
    src, out = args.input, args.output
    pin = json.loads((src / "pin.json").read_bytes())
    spec = importlib.util.spec_from_file_location("factory_verifier", src / "factory_verifier.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.FactoryFinalVerifier(
        pin,
        worker_path=src / "harness/domains/swe_agents/environment/factory_worker.py",
        confinement_path=src / "harness/adversary/execution/confinement.py",
    )  # validates exact task/image/receipt/test identifiers
    root = Path("/factory_boy")
    os.chdir(root)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    def run(
        argv: list[str], name: str, *, allow_failure: bool = False
    ) -> subprocess.CompletedProcess:
        started = time.monotonic()
        result = subprocess.run(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
        (out / (name + ".log")).write_bytes(result.stdout)
        (out / (name + ".command.json")).write_text(
            json.dumps(
                {
                    "argv": argv,
                    "exit_code": result.returncode,
                    "seconds": time.monotonic() - started,
                    "cwd": str(root),
                    "env": env,
                },
                indent=2,
            )
            + "\n"
        )
        if result.returncode and not allow_failure:
            raise RuntimeError(name + " failed")
        return result

    head = run(["git", "rev-parse", "HEAD"], "head").stdout.decode().strip()
    if head != verifier.COMMIT:
        raise ValueError("source revision mismatch")
    if run(["git", "status", "--porcelain", "--untracked-files=no"], "pristine").stdout:
        raise ValueError("image has tracked modifications")

    def sources() -> dict[str, str]:
        result = {}
        for path in sorted((root / "factory").rglob("*.py")):
            if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                raise ValueError("symlink source refused")
            result[path.relative_to(root).as_posix()] = path.read_bytes().decode("utf-8")
        return result

    pristine = sources()
    (out / "pristine-sources.json").write_text(json.dumps(pristine, sort_keys=True) + "\n")
    test = src / "test.patch"
    if test.read_bytes() != pin["test_patch"].encode():
        raise ValueError("test patch mismatch")
    run(["git", "apply", "--check", str(test)], "test-check")
    run(["git", "apply", str(test)], "test-apply")
    if args.phase == "gold":
        gold = src / "gold.patch"
        if gold.read_bytes() != pin["gold_patch"].encode():
            raise ValueError("gold patch mismatch")
        run(["git", "apply", "--check", str(gold)], "gold-check")
        run(["git", "apply", str(gold)], "gold-apply")
    elif args.phase == "candidate":
        candidate = dict(pristine)
        candidate["factory/declarations.py"] = (src / "candidate.py").read_bytes().decode("utf-8")
        verifier.admit_restricted_sources(pristine, candidate)
        (root / "factory/declarations.py").write_bytes(
            candidate["factory/declarations.py"].encode()
        )
    current = sources()
    admission = verifier.admit_restricted_sources(pristine, current)
    (out / "sources.json").write_text(json.dumps(current, sort_keys=True) + "\n")
    test_bytes = (root / "tests/test_regression.py").read_bytes()
    (out / "test_regression.py").write_bytes(test_bytes)
    # The invocation is fixed by this reviewed runner, not supplied by the candidate.
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--no-header",
        "-rA",
        "--tb=line",
        "--color=no",
        "-p",
        "no:cacheprovider",
        "-W",
        "ignore::DeprecationWarning",
        "tests/test_regression.py",
    ]
    if command[3:] != shlex.split(pin["test_command"])[1:]:
        raise ValueError("recorded pytest command differs")
    result = run(command, "test", allow_failure=True)
    if sources() != current or (root / "tests/test_regression.py").read_bytes() != test_bytes:
        raise ValueError("source or test changed during evaluation")
    (out / "result.json").write_text(
        json.dumps(
            {
                "kind": "factory_restricted_repair_trial_v1",
                "phase": args.phase,
                "task_key": pin["key"],
                "scope": "original tests for finite two-token repair grammar only",
                "head": head,
                "image_sha256": pin["image_sha256"],
                "verification_receipt": pin["verification_receipt"],
                "pin_sha256": digest((src / "pin.json").read_bytes()),
                "declarations_sha256": digest(current["factory/declarations.py"].encode()),
                "test_sha256": digest(test_bytes),
                "test_exit_code": result.returncode,
                "admission": admission,
                "python": sys.executable,
                "python_version": sys.version,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
