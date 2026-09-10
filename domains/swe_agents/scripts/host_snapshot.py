"""Build a byte-preserving prepared checkout with no inherited Git objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from domains.swe_agents.environment.interactive_runtime import tree_digest


def worktree_manifest(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts[0] == ".git":
            continue
        if ".git" in rel.parts:
            raise ValueError("nested Git metadata is not an admissible prepared file")
        mode = path.lstat().st_mode & 0o777
        if path.is_symlink():
            raise ValueError("prepared snapshot must not contain symlinks")
        if path.is_file():
            result[str(rel)] = [mode, hashlib.sha256(path.read_bytes()).hexdigest()]
        elif path.is_dir():
            result[str(rel)] = [mode, "directory"]
        else:
            raise ValueError("nonregular prepared snapshot entry")
    return result


def snapshot(source_pin: Path, destination: Path) -> dict:
    pin = json.loads(source_pin.read_text())
    source = Path(pin["repository"])
    if tree_digest(source) != pin["repository_sha256"]:
        raise ValueError("source repository pin mismatch")
    if tree_digest(Path(pin["venv"]), allow_system_links=True) != pin["venv_sha256"]:
        raise ValueError("source venv pin mismatch")
    before = worktree_manifest(source)
    destination.mkdir(parents=True, exist_ok=False)
    repo = destination / "repository"
    shutil.copytree(
        source, repo, ignore=lambda root, names: [".git"] if Path(root) == source else []
    )
    if worktree_manifest(repo) != before:
        raise ValueError("snapshot changed prepared worktree bytes or modes")
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "Prepared snapshot",
        "GIT_AUTHOR_EMAIL": "snapshot@localhost",
        "GIT_COMMITTER_NAME": "Prepared snapshot",
        "GIT_COMMITTER_EMAIL": "snapshot@localhost",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
    }

    def git(*args: str) -> str:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(repo), *args],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--template=", "--initial-branch=prepared")
    git("-c", "core.hooksPath=/dev/null", "add", "--all", "--force")
    git(
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "Freeze prepared task snapshot",
    )
    head = git("rev-parse", "HEAD")
    objects = set(
        git("cat-file", "--batch-all-objects", "--batch-check=%(objectname)").splitlines()
    )
    reachable = {line.split()[0] for line in git("rev-list", "--objects", "--all").splitlines()}
    if objects != reachable or git("rev-list", "--all", "--count") != "1":
        raise ValueError("unexpected inherited or unreachable Git objects")
    if git("rev-list", "--parents", "-n", "1", "HEAD") != head or git("remote"):
        raise ValueError("snapshot has history or remotes")
    if (repo / ".git/objects/info/alternates").exists():
        raise ValueError("snapshot has object alternates")
    if worktree_manifest(repo) != before:
        raise ValueError("Git initialization changed prepared file bytes")
    git("fsck", "--full", "--no-reflogs")
    updated = dict(pin, repository=str(repo), repository_sha256=tree_digest(repo))
    (destination / "host-runtime-pin.json").write_text(json.dumps(updated, indent=2) + "\n")
    (destination / "prepared-ref.txt").write_text(head + "\n")
    (destination / "baseline-untracked.json").write_text("{}\n")
    for name in ("original-pin.json", "gold.patch", "test.patch"):
        candidate = source_pin.parent / name
        if candidate.exists():
            shutil.copyfile(candidate, destination / name)
    receipt = {
        "source_pin": str(source_pin),
        "original_task_commit": pin["commit"],
        "prepared_ref": head,
        "worktree_preserved": True,
        "venv_unchanged": True,
        "commit_count": 1,
        "object_count": len(objects),
        "unreachable_objects": [],
        "remotes": [],
        "alternates": False,
        "repository_sha256": updated["repository_sha256"],
    }
    (destination / "history-containment.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_pin", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source_pin, args.destination), indent=2))
