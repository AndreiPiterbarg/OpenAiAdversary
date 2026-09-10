"""Exercise the real broker locally; scheduler acceptance needs the live smoke receipt."""

import os
import shlex
import sys
from pathlib import Path

import pytest

from domains.swe_agents.environment.pyxis import PyxisRuntime, PyxisSession
from domains.swe_agents.environment.runtime import RuntimeUnavailable

WORKER = Path(__file__).resolve().parents[1] / "domains/swe_agents/environment/pyxis_worker.py"


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PCODE_PRIVATE_TEST", "must-not-inherit")
    value = PyxisSession([sys.executable, "-u", str(WORKER)], 10)
    yield value
    value.stop()


def test_command_uses_scheduler_without_immediate_or_named_shared_image():
    argv = PyxisRuntime(seconds=120).argv("/image.sqsh", "/task")
    assert "--qos=guest-dev" in argv
    assert "--time=2:00" in argv
    assert "--export=NONE" in argv
    assert "--container-writable" in argv
    assert not any(a.startswith(("--immediate", "--nodelist", "--container-name=")) for a in argv)
    assert argv.count("--nodes=1") == 1


def test_repeated_commands_keep_files_but_do_not_inherit_credentials(session):
    session.write_file("value", "one\ntwo")
    assert session.exec("cat value; printf three >> value", 5) == (0, "one\ntwo", "")
    assert session.read_file("value") == "one\ntwothree"
    assert session.exec('printf %s "${PCODE_PRIVATE_TEST-unset}"', 5)[1] == "unset"
    code, out, err = session.exec("printf output; printf error >&2; exit 7", 5)
    assert (code, out, err) == (7, "output", "error")


def test_binary_and_unicode_output_is_bounded_protocol_text(session):
    assert session.exec("printf '\\377'", 5)[1] == "\ufffd"
    session.write_file("unicode file", "π雪")
    assert session.read_file("unicode file") == "π雪"


def test_timeout_aborts_session_and_reaps_broker(session):
    with pytest.raises(RuntimeUnavailable, match="timed out"):
        session.exec("sleep 30", 0.05)
    assert session.closed
    assert session.process.poll() is not None
    with pytest.raises(RuntimeError, match="closed"):
        session.exec("true", 1)


def test_output_flood_aborts_session(session):
    command = shlex.quote(sys.executable) + " -c \"print('x' * 4000001)\""
    with pytest.raises(RuntimeUnavailable, match="audit limit"):
        session.exec(command, 5)
    assert session.process.poll() is not None


def test_broker_startup_failure_includes_launcher_diagnostic():
    with pytest.raises(RuntimeUnavailable, match="launcher failed"):
        PyxisSession([sys.executable, "-c", "import sys; sys.stderr.write('launcher failed')"], 5)


def test_stop_exits_cleanly_and_is_idempotent(session):
    session.stop()
    assert session.process.returncode == 0
    session.stop()


def test_snapshot_tracks_edits_after_agent_commit(session):
    # Real filesystem hashes still detect changes after the index is rewritten.
    session.exec(
        "git init -q; git config user.email test@example.invalid; git config user.name Test", 5
    )
    session.write_file("tracked", "before")
    session.exec("git add tracked; git commit -qm initial", 5)
    session._baseline = session._files()
    session._packages = session._installed()
    session.write_file("tracked", "after")
    session.exec("git add tracked; git commit -qm changed", 5)
    assert session.exec("git status --porcelain", 5)[1] == ""
    assert session.snapshot()["changed_files"] == ["tracked"]


def test_file_paths_are_not_shell_code(session):
    name = "$(touch escaped); quoted file"
    session.write_file(name, "literal")
    assert session.read_file(name) == "literal"
    assert not os.path.exists("escaped")


def test_v1_launch_activates_recorded_conda_environment():
    argv = PyxisRuntime().argv("/image.sqsh", "/testbed", "conda_testbed")
    assert "--container-workdir=/testbed" in argv
    assert "conda activate testbed;" in argv[-1]
    assert "exec python -u -c " in argv[-1]
    with pytest.raises(ValueError, match="unsupported Python environment"):
        PyxisRuntime().argv("/image.sqsh", "/", "invented")
