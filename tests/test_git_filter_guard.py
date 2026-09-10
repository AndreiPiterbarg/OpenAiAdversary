"""Live Linux Git-filter escape regression; no model or scheduler calls are needed."""

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from domains.swe_agents.environment import target_guard


@pytest.mark.skipif(sys.platform != "linux", reason="requires real Linux Landlock/seccomp")
def test_candidate_git_filter_runs_inside_guard_for_check_and_apply(tmp_path):
    repo, scratch = tmp_path / "repo", tmp_path / "scratch"
    repo.mkdir()
    scratch.mkdir()
    outside = tmp_path / "outside-write"

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (repo / "tracked.txt").write_text("BEFORE\n")
    git("add", "tracked.txt")
    git("commit", "-qm", "baseline")
    # This configuration is pristine; arbitrary candidate artifacts add the
    # attributes and filter source before raw Git would previously invoke them.
    executable = Path(sys.executable)
    if not all(
        any(Path(root) in path.parents for root in ("/usr", "/opt"))
        for path in (executable, executable.resolve())
    ):
        executable = Path("/usr/bin/python3")
    assert executable.is_file(), "a readonly Python interpreter is required"
    filter_command = shlex.quote(str(executable)) + " -I filter.py "
    git("config", "filter.audit.clean", filter_command + "clean")
    git("config", "filter.audit.smudge", filter_command + "smudge")
    git("config", "filter.audit.required", "true")
    (repo / ".gitattributes").write_text("tracked.txt filter=audit\n")
    (repo / "filter.py").write_text(
        "import pathlib,sys\n"
        f'try: pathlib.Path({str(outside)!r}).write_text("escaped")\n'
        'except PermissionError: pathlib.Path("filter-blocked").write_text("yes")\n'
        'else: raise RuntimeError("guard escaped")\n'
        "data=sys.stdin.read()\n"
        "sys.stdout.write(data.upper() if sys.argv[1]=='clean' else data.lower())\n"
    )
    # A transformed worktree preimage requires Git to run the clean filter;
    # versions that skip filters for an already-matching preimage cannot bypass
    # this regression's invocation assertion.
    (repo / "tracked.txt").write_text("before\n")
    patch = scratch / "candidate.patch"
    patch.write_text(
        "diff --git a/tracked.txt b/tracked.txt\n"
        "--- a/tracked.txt\n+++ b/tracked.txt\n@@ -1 +1 @@\n-BEFORE\n+AFTER\n"
    )
    guard = [
        sys.executable,
        "-I",
        str(Path(target_guard.__file__).resolve()),
        "--repo",
        str(repo.resolve()),
        "--scratch",
        str(scratch.resolve()),
        "--",
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-c",
    ]
    for flags in ("--check ", ""):
        (repo / "filter-blocked").unlink(missing_ok=True)
        result = subprocess.run(
            guard + ["git apply " + flags + "-- " + shlex.quote(str(patch))],
            capture_output=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr.decode()
        assert (repo / "filter-blocked").is_file(), result.stderr.decode()
        assert (repo / "filter-blocked").read_text() == "yes", result.stderr.decode()
        assert not outside.exists()
    assert (repo / "tracked.txt").read_text() == "after\n"
