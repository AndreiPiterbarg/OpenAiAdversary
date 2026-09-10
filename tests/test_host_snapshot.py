import json
import os
import subprocess
from pathlib import Path

from domains.swe_agents.environment.interactive_runtime import tree_digest
from domains.swe_agents.scripts.host_snapshot import snapshot, worktree_manifest


def test_snapshot_removes_reachable_and_unreachable_future_objects(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    env = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_AUTHOR_NAME="test",
        GIT_AUTHOR_EMAIL="test@localhost",
        GIT_COMMITTER_NAME="test",
        GIT_COMMITTER_EMAIL="test@localhost",
    )

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(source), *args], env=env, text=True
        ).strip()

    git("init", "--template=")
    (source / "task.py").write_text("baseline\n")
    git("add", ".")
    git("commit", "-m", "baseline")
    baseline = git("rev-parse", "HEAD")
    (source / "task.py").write_text("GOLD FUTURE SECRET\n")
    git("commit", "-am", "future gold")
    future = git("rev-parse", "HEAD")
    git("reset", "--hard", baseline)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "metadata").write_text("fixed")
    pin = tmp_path / "pin.json"
    pin.write_text(
        json.dumps(
            {
                "repository": str(source),
                "repository_sha256": tree_digest(source),
                "venv": str(venv),
                "venv_sha256": tree_digest(venv),
                "commit": baseline,
                "task_key": "example",
            }
        )
    )
    before = worktree_manifest(source)
    receipt = snapshot(pin, tmp_path / "new")
    assert receipt["commit_count"] == 1
    assert receipt["unreachable_objects"] == []
    assert worktree_manifest(tmp_path / "new/repository") == before
    result = subprocess.run(
        ["git", "-C", str(tmp_path / "new/repository"), "show", future], capture_output=True
    )
    assert result.returncode != 0
    assert b"GOLD FUTURE SECRET" not in result.stdout
