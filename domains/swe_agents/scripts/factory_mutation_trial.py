"""Run pre-reviewed negative fixtures; this is never admission of arbitrary model code.

Original frozen tests and independent supplementary tests are kept separate.
Candidate test changes are rejected and never installed as trusted verifier inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    args = parser.parse_args()
    src, out, repo = Path("/va-input"), Path("/va-output"), Path("/factory_boy")
    fixture = json.loads((src / "fixtures" / f"{args.case}.json").read_bytes())
    assert fixture["name"] == args.case
    pin = json.loads((src / "pin.json").read_bytes())
    os.chdir(repo)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(repo),
    }

    def run(argv: list[str], name: str, allowed: bool = False) -> dict:
        started = time.monotonic()
        result = subprocess.run(
            argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90, check=False
        )
        (out / (name + ".log")).write_bytes(result.stdout)
        record = {
            "argv": argv,
            "exit_code": result.returncode,
            "seconds": time.monotonic() - started,
            "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        }
        (out / (name + ".command.json")).write_text(json.dumps(record, indent=2) + "\n")
        if not allowed and result.returncode:
            raise RuntimeError(name + " failed")
        return record

    run(["git", "rev-parse", "HEAD"], "head")
    assert (out / "head.log").read_text().strip() == pin["commit"]
    run(["git", "status", "--porcelain", "--untracked-files=no"], "pristine")
    assert not (out / "pristine.log").read_bytes()
    pristine = {
        p.relative_to(repo).as_posix(): p.read_bytes().decode()
        for p in sorted((repo / "factory").rglob("*.py"))
    }
    assert pristine == json.loads((src / "pristine-sources.json").read_bytes())
    run(["git", "apply", "--check", str(src / "test.patch")], "test-check")
    run(["git", "apply", str(src / "test.patch")], "test-apply")
    test_path = repo / "tests/test_regression.py"
    tests = test_path.read_bytes()
    assert tests == (src / "test_regression.py").read_bytes()
    spec = importlib.util.spec_from_file_location("factory_verifier", src / "factory_verifier.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    rejection = None
    try:
        if fixture["test_source"].encode() != tests:
            raise ValueError("candidate changes protected tests")
        verifier.admit_restricted_sources(pristine, fixture["candidate_sources"])
    except ValueError as exc:
        rejection = str(exc)
    # Diagnostic execution is limited to these reviewed source fixtures, not candidate exports.
    assert set(fixture["candidate_sources"]) == set(pristine)
    for path, source in fixture["candidate_sources"].items():
        if path != "factory/declarations.py":
            assert source == pristine[path]
    declarations = repo / "factory/declarations.py"
    declarations.write_bytes(fixture["candidate_sources"]["factory/declarations.py"].encode())
    original = run(
        [
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
        ],
        "original",
        True,
    )
    supplementary = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--no-header",
            "-rA",
            "--tb=line",
            "--color=no",
            "-p",
            "no:cacheprovider",
            "--confcutdir=/va-input",
            "/va-input/factory_challenges.py",
        ],
        "supplementary",
        True,
    )
    assert (
        declarations.read_bytes()
        == fixture["candidate_sources"]["factory/declarations.py"].encode()
    )
    assert test_path.read_bytes() == tests
    (out / "result.json").write_text(
        json.dumps(
            {
                "kind": "reviewed_factory_mutation_diagnostic_v1",
                "case": args.case,
                "admission_rejection": rejection,
                "original": original,
                "supplementary": supplementary,
                "source_sha256": hashlib.sha256(declarations.read_bytes()).hexdigest(),
                "test_sha256": hashlib.sha256(tests).hexdigest(),
                "fixture_sha256": hashlib.sha256(
                    (src / "fixtures" / f"{args.case}.json").read_bytes()
                ).hexdigest(),
                "test_changes_executed": False,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
