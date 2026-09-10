"""Offline launcher helpers and ownership checks; no GPU/server launches."""

import json
import os

import pytest

from domains.swe_agents.scripts import throughput_serve as serve


def settings(tmp_path):
    return serve.Settings(
        tmp_path / "out", tmp_path / "prior", "/venv/bin/python", "/other/bin/vllm"
    )


def test_settings_keep_registered_serving_arm_and_sanitize_env(tmp_path, monkeypatch):
    config = settings(tmp_path)
    argv = serve.argv_for(config, "/cache/snapshot", 18103)
    assert argv[:4] == ["/venv/bin/python", "/other/bin/vllm", "serve", "/cache/snapshot"]
    for name, value in (
        ("--host", "127.0.0.1"),
        ("--max-num-seqs", "16"),
        ("--max-model-len", "16384"),
    ):
        assert argv[argv.index(name) + 1] == value
    assert "--enforce-eager" not in argv
    monkeypatch.setenv("OPENAI_API_KEY", "must not inherit")
    env = serve.environment_for(config, "GPU-exact-uuid")
    assert "OPENAI_API_KEY" not in env
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-exact-uuid"
    assert env["VLLM_USE_FLASHINFER_SAMPLER"] == "0"
    assert env["OMP_NUM_THREADS"] == "4"
    assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["PATH"].startswith("/venv/bin:/other/bin:")


@pytest.mark.parametrize(
    "changes",
    [{"python": "python"}, {"port_base": 65535}, {"readiness_seconds": 0}, {"stagger_seconds": -1}],
)
def test_invalid_settings_refuse(tmp_path, changes):
    params = vars(settings(tmp_path)) | changes
    with pytest.raises(ValueError):
        serve.Settings(**params)


def test_cached_pin_sizes_are_checked_offline(tmp_path):
    config = settings(tmp_path)
    config.prior.mkdir()
    snapshot = tmp_path / serve.REV
    snapshot.mkdir()
    (snapshot / "weights").write_bytes(b"abc")
    (config.prior / "model-pin.json").write_text(
        json.dumps(
            {
                "repo": serve.REPO,
                "revision": serve.REV,
                "selected_files": [{"name": "weights", "size": 3}],
            }
        )
    )
    (config.prior / "snapshot.json").write_text(
        json.dumps({"revision": serve.REV, "path": str(snapshot)})
    )
    assert serve.cached_snapshot(config)[1]["path"] == str(snapshot)
    (snapshot / "weights").write_bytes(b"shorter or longer")
    with pytest.raises(ValueError, match="size"):
        serve.cached_snapshot(config)
    assert not config.root.exists()


def test_proc_stat_handles_parentheses_in_comm(tmp_path):
    root = tmp_path / "123"
    root.mkdir()
    fields = ["S", "1", "123"] + ["0"] * 16 + ["7654"]
    (root / "stat").write_text("123 (name (with) spaces) " + " ".join(fields))
    assert serve.process_identity(123, tmp_path) == {
        "pid": 123,
        "starttime": 7654,
        "pgid": 123,
        "uid": os.getuid(),
    }


@pytest.mark.parametrize("changed", [False, True])
def test_shutdown_never_signals_reused_pid(tmp_path, monkeypatch, changed):
    owned = {"pid": 123, "starttime": 456, "pgid": 123, "uid": os.getuid()}
    (tmp_path / "servers.json").write_text(
        json.dumps({"0": {"ownership": owned}, "1": {"state": "skipped_occupied"}})
    )
    monkeypatch.setattr(
        serve, "process_identity", lambda pid: owned | ({"starttime": 999} if changed else {})
    )
    killed = []
    monkeypatch.setattr(serve.os, "killpg", lambda pid, signal: killed.append(pid))
    result = serve.stop_owned(tmp_path)
    assert killed == ([] if changed else [123])
    assert result["0"] == ("identity_changed_refused" if changed else "term_sent")
    assert result["1"] == "no_owned_identity"


def test_main_is_import_safe_and_parameterized(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(serve, "launch", calls.append)
    serve.main(
        [
            "--root",
            str(tmp_path / "out"),
            "--prior",
            str(tmp_path / "old"),
            "--python",
            "/custom/python",
            "--vllm",
            "/custom/vllm",
        ]
    )
    assert len(calls) == 1 and calls[0].python == "/custom/python"
    assert not (tmp_path / "out").exists()


def test_effective_proc_environment_and_argv_are_verified(tmp_path):
    root = tmp_path / "123"
    root.mkdir()
    fields = ["S", "1", "123"] + ["0"] * 16 + ["7654"]
    (root / "stat").write_text("123 (python) " + " ".join(fields))
    env = serve.environment_for(settings(tmp_path), "GPU-uuid")
    (root / "environ").write_bytes(
        b"\0".join(f"{key}={env[key]}".encode() for key in serve.ENV_KEYS)
    )
    argv = ["/python", "/vllm", "serve"]
    (root / "cmdline").write_bytes(b"\0".join(x.encode() for x in argv) + b"\0")
    result = serve.process_receipt(123, env, argv, tmp_path)
    assert result["effective_argv"] == argv
    assert result["effective_environment"]["CUDA_VISIBLE_DEVICES"] == "GPU-uuid"
    (root / "environ").write_bytes(b"CUDA_VISIBLE_DEVICES=wrong\0")
    with pytest.raises(RuntimeError, match="environment differs"):
        serve.process_receipt(123, env, argv, tmp_path)


def test_first_replica_is_ready_before_second_launch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    config = settings(tmp_path)
    monkeypatch.setattr(serve, "cached_snapshot", lambda _: ({}, {"path": "/cached"}))
    monkeypatch.setattr(
        serve, "gpu_rows", lambda: [["0", "GPU-a", "0", "0"], ["1", "GPU-b", "0", "0"]]
    )
    monkeypatch.setattr(
        serve.subprocess,
        "check_output",
        lambda argv, **kw: "{}" if argv[0] == config.python else "",
    )
    monkeypatch.setattr(serve.time, "sleep", lambda _: None)
    events = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            assert address[0] == "127.0.0.1"

    monkeypatch.setattr(serve.socket, "socket", Socket)

    def popen(argv, **kwargs):
        events.append("launch")
        assert kwargs["start_new_session"] is True
        return SimpleNamespace(pid=100 + events.count("launch"), poll=lambda: None)

    monkeypatch.setattr(serve.subprocess, "Popen", popen)
    monkeypatch.setattr(
        serve,
        "process_identity",
        lambda pid: {"pid": pid, "pgid": pid, "starttime": 1, "uid": os.getuid()},
    )
    monkeypatch.setattr(serve, "process_receipt", lambda *a: {"verified_fixture": True})
    monkeypatch.setattr(serve, "healthy", lambda port: events.append("healthy") or {"data": []})
    serve.launch(config)
    assert events[:3] == ["launch", "healthy", "launch"]
    result = json.loads((config.root / "status.json").read_text())
    assert result["ready"] == 2
