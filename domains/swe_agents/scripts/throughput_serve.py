"""Offline pinned vLLM launcher; importing this module never launches processes."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = "mistralai/Devstral-Small-2-24B-Instruct-2512"
REV = "55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128"
ENV_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "VLLM_USE_FLASHINFER_SAMPLER",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "OMP_NUM_THREADS",
)


@dataclass(frozen=True)
class Settings:
    root: Path
    prior: Path
    python: str = sys.executable
    vllm: str = str(Path(sys.executable).parent / "vllm")
    port_base: int = 18100
    readiness_seconds: float = 1200
    stagger_seconds: float = 5

    def __post_init__(self) -> None:
        if not 1024 <= self.port_base <= 65520:
            raise ValueError("invalid port base")
        if self.readiness_seconds <= 0 or self.stagger_seconds < 0:
            raise ValueError("invalid launch timing")
        if not Path(self.python).is_absolute() or not Path(self.vllm).is_absolute():
            raise ValueError("interpreter and vLLM paths must be absolute")


def stamp() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def write(root: Path, name: str, value: Any) -> None:
    path = root / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def argv_for(settings: Settings, snapshot: str, port: int) -> list[str]:
    return [
        settings.python,
        settings.vllm,
        "serve",
        snapshot,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--served-model-name",
        "devstral-base-rate",
        "--max-model-len",
        "16384",
        "--gpu-memory-utilization",
        "0.85",
        "--max-num-seqs",
        "16",
        "--tool-call-parser",
        "mistral",
        "--enable-auto-tool-choice",
        "--tokenizer-mode",
        "mistral",
        "--config-format",
        "mistral",
        "--load-format",
        "mistral",
        "--language-model-only",
    ]


def environment_for(settings: Settings, uuid: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(s in k.upper() for s in ("TOKEN", "API_KEY", "SECRET", "PASSWORD"))
    }
    env.update(
        CUDA_VISIBLE_DEVICES=uuid,
        VLLM_USE_FLASHINFER_SAMPLER="0",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        OMP_NUM_THREADS="4",
    )
    env["PATH"] = f"{Path(settings.python).parent}:{Path(settings.vllm).parent}:" + env.get(
        "PATH", "/usr/bin:/bin"
    )
    return env


def process_identity(pid: int, proc: Path = Path("/proc")) -> dict[str, int]:
    root = proc / str(pid)
    # comm can contain spaces and parentheses; fields after its final ')' begin at field 3.
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    return {
        "pid": pid,
        "starttime": int(fields[19]),
        "pgid": int(fields[2]),
        "uid": root.stat().st_uid,
    }


def process_receipt(
    pid: int, expected_env: dict[str, str], argv: list[str], proc: Path = Path("/proc")
) -> dict[str, Any]:
    identity = process_identity(pid, proc)
    raw = (proc / str(pid) / "environ").read_bytes().split(b"\0")
    env = dict(item.decode().split("=", 1) for item in raw if b"=" in item)
    effective = {key: env.get(key) for key in ENV_KEYS}
    if effective != {key: expected_env[key] for key in ENV_KEYS}:
        raise RuntimeError("effective serving environment differs from registered settings")
    if identity["pgid"] != pid or identity["uid"] != os.getuid():
        raise RuntimeError("server is not an owned process group")
    command = (proc / str(pid) / "cmdline").read_bytes().split(b"\0")
    actual = [x.decode() for x in command if x]
    if actual != argv:
        raise RuntimeError("effective server command differs from launch command")
    return {
        **identity,
        "effective_environment": effective,
        "effective_argv": actual,
        "checked": stamp(),
    }


def stop_owned(root: Path) -> dict[str, str]:
    """Signal only recorded groups whose live process identity still matches."""
    result = {}
    servers = json.loads((root / "servers.json").read_text())
    for index, server in servers.items():
        owned = server.get("ownership")
        if not owned:
            result[index] = "no_owned_identity"
            continue
        pid = owned["pid"]
        try:
            live = process_identity(pid)
        except FileNotFoundError:
            result[index] = "already_exited"
            continue
        if live != owned or live["uid"] != os.getuid() or live["pgid"] != pid:
            result[index] = "identity_changed_refused"
            continue
        try:
            os.killpg(pid, signal.SIGTERM)
            result[index] = "term_sent"
        except ProcessLookupError:
            result[index] = "already_exited"
    write(root, "shutdown.json", {"time": stamp(), "results": result})
    return result


def cached_snapshot(settings: Settings) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = json.loads((settings.prior / "model-pin.json").read_text())
    snapshot = json.loads((settings.prior / "snapshot.json").read_text())
    if (
        metadata.get("repo") != REPO
        or metadata.get("revision") != REV
        or snapshot.get("revision") != REV
    ):
        raise ValueError("cached model pin differs")
    root = Path(snapshot["path"])
    if not root.is_absolute() or root.name != REV or not metadata.get("selected_files"):
        raise ValueError("invalid pinned snapshot path or file manifest")
    for item in metadata["selected_files"]:
        name = Path(item["name"])
        if name.is_absolute() or ".." in name.parts or not (root / name).is_file():
            raise ValueError("unsafe or missing cached model file")
        if (root / name).stat().st_size != item["size"]:
            raise ValueError("cached model file size differs")
    return metadata, snapshot


def gpu_rows() -> list[list[str]]:
    return list(
        csv.reader(
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,uuid,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
            ).splitlines()
        )
    )


def healthy(port: int) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("replica is not healthy")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as response:
        models = json.load(response)
    if not any(model["id"] == "devstral-base-rate" for model in models["data"]):
        raise RuntimeError("served model identity differs")
    return models


def launch(settings: Settings) -> None:
    metadata, snapshot = cached_snapshot(settings)
    settings.root.mkdir(parents=True, exist_ok=False)
    write(settings.root, "model-pin.json", metadata)
    write(settings.root, "snapshot.json", snapshot)
    version_code = (
        "import importlib.metadata,json; "
        "print(json.dumps({n:importlib.metadata.version(n) "
        "for n in ['vllm','torch','transformers','mistral_common']}))"
    )
    versions = json.loads(
        subprocess.check_output(
            [settings.python, "-c", version_code], text=True, env=environment_for(settings, "")
        )
    )
    write(settings.root, "runtime-versions.json", versions)
    servers, processes = {}, {}
    initial = {int(row[0]): row[1].strip() for row in gpu_rows()}
    try:
        for index, uuid in initial.items():
            port = settings.port_base + index
            row = next(row for row in gpu_rows() if int(row[0]) == index)
            occupied = subprocess.check_output(
                ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                text=True,
            )
            if row[1].strip() != uuid or float(row[2]) != 0 or uuid in occupied:
                servers[str(index)] = {"state": "skipped_occupied", "observed": row}
                continue
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    servers[str(index)] = {"state": "skipped_port_occupied", "port": port}
                    continue
            argv, env = argv_for(settings, snapshot["path"], port), environment_for(settings, uuid)
            with open(settings.root / f"gpu-{index}.log", "ab", buffering=0) as log:
                process = subprocess.Popen(
                    argv,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            processes[str(index)] = process
            ownership = process_identity(process.pid)
            server = {
                "state": "starting",
                "gpu_uuid": uuid,
                "port": port,
                "pid": process.pid,
                "argv": argv,
                "ownership": ownership,
                "time": stamp(),
            }
            servers[str(index)] = server
            write(settings.root, "servers.json", servers)
            server["deployment_receipt"] = {
                **process_receipt(process.pid, env, argv),
                "runtime_versions": versions,
                "graph_policy": "vllm_default_no_enforce_eager_override",
            }
            if len(processes) == 1:
                deadline = time.monotonic() + settings.readiness_seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("first model replica exited; inspect its log")
                    try:
                        server["models"] = healthy(port)
                        server["state"] = "ready"
                        break
                    except (OSError, ValueError, RuntimeError):
                        time.sleep(5)
                else:
                    raise TimeoutError("first replica did not become ready")
            time.sleep(settings.stagger_seconds)
        deadline = time.monotonic() + settings.readiness_seconds
        while time.monotonic() < deadline:
            pending = False
            for index, server in servers.items():
                if server["state"] not in ("starting", "ready"):
                    continue
                if processes[index].poll() is not None:
                    server["state"] = "exited"
                    continue
                try:
                    server["models"] = healthy(server["port"])
                    server["state"] = "ready"
                except (OSError, ValueError, RuntimeError):
                    server["state"] = "starting"
                    pending = True
            write(settings.root, "servers.json", servers)
            if not pending:
                break
            time.sleep(5)
        ready = sum(server["state"] == "ready" for server in servers.values())
        write(
            settings.root,
            "status.json",
            {
                "phase": "ready" if servers and ready == len(servers) else "incomplete",
                "ready": ready,
                "time": stamp(),
                "servers": servers,
            },
        )
    except BaseException:
        write(settings.root, "servers.json", servers)
        stop_owned(settings.root)
        write(settings.root, "status.json", {"phase": "launch_failed", "time": stamp()})
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=os.environ.get("PRUN_SERVING_ROOT"))
    parser.add_argument("--prior", type=Path, default=os.environ.get("PRUN_PRIOR_SERVING_ROOT"))
    parser.add_argument("--python", default=os.environ.get("PRUN_SERVING_PYTHON", sys.executable))
    parser.add_argument(
        "--vllm",
        default=os.environ.get("PRUN_VLLM_PATH", str(Path(sys.executable).parent / "vllm")),
    )
    parser.add_argument("--port-base", type=int, default=18100)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)
    if args.root is None or (not args.stop and args.prior is None):
        parser.error("--root and, for launch, --prior are required")
    if args.stop:
        stop_owned(args.root)
    else:
        launch(Settings(args.root, args.prior, args.python, args.vllm, args.port_base))


if __name__ == "__main__":
    main()
