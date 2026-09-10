"""Host adapter pinning/refusal checks, without running a model or a host guard."""

import os
import sys
from pathlib import Path

import pytest

from domains.swe_agents.environment.interactive_runtime import (
    HostRuntimePin,
    HostSession,
    InteractiveRuntime,
    tree_digest,
)
from domains.swe_agents.environment.runtime import RuntimeUnavailable


def test_tree_digest_binds_contents_and_modes(tmp_path):
    root = tmp_path.resolve()
    file = root / "source.py"
    file.write_bytes(b"hello\0")
    first = tree_digest(root)
    file.write_bytes(b"other\0")
    assert tree_digest(root) != first
    second = tree_digest(root)
    file.chmod(0o755)
    assert tree_digest(root) != second


def test_tree_digest_refuses_fifo_and_symlink(tmp_path):
    root = tmp_path.resolve()
    os.mkfifo(root / "fifo")
    with pytest.raises(ValueError, match="nonregular"):
        tree_digest(root)
    (root / "fifo").unlink()
    (root / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlink"):
        tree_digest(root)


def test_no_default_host_boundary_can_expose_raw_session(tmp_path):
    pin = HostRuntimePin(
        "Factory", "commit", tmp_path, "digest", tmp_path, "digest", Path("/usr/bin/python3")
    )
    runtime = InteractiveRuntime(pin)
    with pytest.raises(RuntimeUnavailable, match="aggregate resource boundary"):
        runtime.start_guarded()


@pytest.mark.skipif(sys.platform != "linux", reason="host process ownership uses Linux procfs")
def test_raw_broker_bounded_transport_and_cleanup(tmp_path):
    root = tmp_path / "session"
    root.mkdir()
    repo = root / "repo"
    repo.mkdir()
    pin = HostRuntimePin(
        "Factory", "commit", repo, "digest", tmp_path, "digest", Path(sys.executable)
    )
    session = HostSession(root, repo, pin)
    try:
        code, out, err = session.exec("printf 'hello'", 2)
        assert (code, out, err) == (0, "hello", "")
        session.write_file("source.py", "hello\n")
        assert session.read_file("source.py") == "hello\n"
        with pytest.raises(RuntimeUnavailable, match="private session"):
            session.write_file(str(tmp_path / "escape"), "bad")
        with pytest.raises(RuntimeUnavailable, match="snapshots"):
            session.snapshot()
    finally:
        session.stop()
    assert not root.exists()
    assert session.process.poll() is not None


def test_venv_internal_directory_link_is_bound_without_following_escape(tmp_path):
    root = tmp_path.resolve()
    (root / "lib").mkdir()
    (root / "lib/site.py").write_text("value=1")
    (root / "lib64").symlink_to("lib")
    first = tree_digest(root, allow_system_links=True)
    (root / "lib/site.py").write_text("value=2")
    assert tree_digest(root, allow_system_links=True) != first


def test_materialized_tracked_link_requires_a_new_prepared_checkpoint(tmp_path):
    import shutil
    import subprocess

    from domains.swe_agents.environment.interactive_runtime import require_clean_prepared_tree

    source = tmp_path / "source"
    source.mkdir()

    def git(root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git(source, "init", "-q")
    git(source, "config", "user.name", "Test")
    git(source, "config", "user.email", "test@invalid")
    (source / "notes.txt").write_text("trusted documentation\n")
    (source / "ChangeLog").symlink_to("notes.txt")
    git(source, "add", ".")
    git(source, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    copied = tmp_path / "copied"
    shutil.copytree(source, copied, symlinks=False)
    with pytest.raises(RuntimeUnavailable, match="Git checkpoint"):
        require_clean_prepared_tree(copied)
    git(copied, "add", "ChangeLog")
    git(copied, "-c", "commit.gpgsign=false", "commit", "-qm", "Freeze materialized documentation")
    before = tree_digest(copied.resolve())
    require_clean_prepared_tree(copied)
    assert tree_digest(copied.resolve()) == before
