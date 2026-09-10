"""Startup inputs cannot redirect trusted broker or guard launches into candidate code."""

import json
import os
import shlex

import pytest

from domains.swe_agents.environment import pyxis_worker
from domains.swe_agents.environment.guarded_session import GuardedSession, install_guard
from domains.swe_agents.environment.runtime import RuntimeUnavailable


class Raw:
    def __init__(self, executable="/opt/conda/envs/testbed/bin/python", resolved=None):
        self.executable = executable
        self.resolved = resolved or executable
        self.commands = []
        self.files = {}

    def exec(self, command, timeout):
        self.commands.append(command)
        if command.startswith("python -I -c"):
            return 0, json.dumps({"executable": self.executable, "resolved": self.resolved}), ""
        if command.startswith("mktemp"):
            return 0, "/tmp/prun-guard-abc\n", ""
        if command.startswith("mkdir"):
            return 0, "", ""
        return (
            0,
            json.dumps(
                dict.fromkeys(
                    ["/proc/self/status", "/proc/1/mem", "network", "signal", "system_write"],
                    True,
                )
            ),
            "",
        )

    def write_file(self, path, source):
        self.files[path] = source


def test_install_pins_pristine_venv_path_and_all_later_guard_launches_are_absolute():
    raw = Raw(resolved="/opt/conda/bin/python3.11")
    guarded = install_guard(raw, "/repo")
    guarded.exec("python candidate.py")
    argv = shlex.split(raw.commands[-1])
    assert argv[0] == "/opt/conda/envs/testbed/bin/python"
    assert argv[1] == "-I"
    assert guarded.attestation["python_executable"] == argv[0]
    assert argv[-1] == "python candidate.py"  # This command only runs after confinement.


@pytest.mark.parametrize(
    "executable,resolved",
    [
        ("/repo/.venv/bin/python", "/usr/bin/python3"),
        ("/usr/bin/python3", "/repo/fake-python"),
        ("python", "/usr/bin/python3"),
        ("/usr/../repo/python", "/repo/python"),
    ],
)
def test_candidate_interpreter_paths_are_refused_before_guard_preparation(executable, resolved):
    raw = Raw(executable, resolved)
    with pytest.raises(RuntimeUnavailable, match="readonly"):
        install_guard(raw, "/repo")
    assert len(raw.commands) == 1 and not raw.files


def test_direct_guard_constructor_cannot_select_repository_interpreter():
    with pytest.raises(RuntimeUnavailable, match="readonly"):
        GuardedSession(
            Raw(), "/repo", "/scratch", "/guard", b"guard", python_executable="/repo/python"
        )


def test_broker_scrubs_startup_hooks_and_repository_command_path(tmp_path):
    malicious = tmp_path / "bin"
    malicious.mkdir()
    env = pyxis_worker.trusted_command_environment(
        {
            "PATH": str(malicious) + os.pathsep + "/usr/bin:/bin",
            "BASH_ENV": str(tmp_path / "startup.sh"),
            "ENV": str(tmp_path / "startup.sh"),
            "PYTHONPATH": str(tmp_path),
            "PYTHONHOME": str(tmp_path),
            "PYTHONSTARTUP": str(tmp_path / "startup.py"),
            "LD_PRELOAD": str(tmp_path / "attack.so"),
            "BASH_FUNC_python%%": "() { echo malicious; }",
            "LANG": "C",
        }
    )
    assert str(malicious) not in env["PATH"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "PYTHONNOUSERSITE": "1"}


def test_broker_real_shell_does_not_source_bash_env(tmp_path, monkeypatch):
    marker = tmp_path / "executed"
    startup = tmp_path / "startup.sh"
    startup.write_text("touch " + shlex.quote(str(marker)) + "\n")
    env = pyxis_worker.trusted_command_environment(
        {
            "PATH": "/usr/bin:/bin",
            "BASH_ENV": str(startup),
            "ENV": str(startup),
        }
    )
    monkeypatch.setattr(pyxis_worker, "_COMMAND_ENVIRONMENT", env)
    result = pyxis_worker.execute("printf guarded-launch", 5)
    assert result["exit"] == 0 and result["stdout"] == "guarded-launch"
    assert not marker.exists()


def test_broker_rejects_entirely_writable_path(tmp_path):
    with pytest.raises(RuntimeError, match="readonly"):
        pyxis_worker.trusted_command_environment({"PATH": str(tmp_path)})


def test_conda_path_order_is_preserved_without_repository_entries(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr(Path, "resolve", lambda self: self)
    env = pyxis_worker.trusted_command_environment(
        {
            "PATH": "/repo/.venv/bin:/opt/conda/envs/testbed/bin:/opt/conda/bin:/usr/bin",
        }
    )
    assert env["PATH"] == "/opt/conda/envs/testbed/bin:/opt/conda/bin:/usr/bin"


def test_system_path_symlink_into_repository_is_excluded(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr(
        Path, "resolve", lambda self: Path("/repo/bin") if str(self) == "/opt/linked/bin" else self
    )
    env = pyxis_worker.trusted_command_environment({"PATH": "/opt/linked/bin:/usr/bin"})
    assert env["PATH"] == "/usr/bin"
