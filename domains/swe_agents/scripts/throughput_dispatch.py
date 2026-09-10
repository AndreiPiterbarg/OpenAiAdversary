"""Cluster-local diagnostic throughput arms with global staggering and owned cleanup.

Run separate K=3, K=4 and K=6 invocations; compare their immutable registrations rather
than pooling outcomes. This module also supplies isolated worker/controller entrypoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domains.swe_agents.scripts.episode_budget import EpisodeBudget
from domains.swe_agents.scripts.local_episode_bridge import (
    CANONICAL_MODEL,
    MODEL_REVISION,
    run_local_bridge,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Node(Strict):
    name: str = Field(pattern=r"^worker-[0-9]+$")
    cpus: int = Field(strict=True, gt=0)
    memory_mb: int = Field(strict=True, gt=0)


class Task(Strict):
    key: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    pin: Path
    corpus: str = "unspecified"


class DispatchConfig(Strict):
    arm_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    allocation_id: str = Field(pattern=r"^[0-9]+$")
    nodes: list[Node] = Field(min_length=1)
    endpoints: list[str] = Field(min_length=1)
    k: int = Field(strict=True)
    tasks: list[Task] = Field(min_length=1)
    source_root: Path
    source_manifest: Path
    python: Path
    duration_seconds: float = Field(gt=0)
    stagger_seconds: float = Field(default=3, ge=0)
    budget: EpisodeBudget = Field(default_factory=EpisodeBudget)
    server_settings: dict[str, Any]
    release_source_before_replay: bool = Field(default=False, strict=True)

    @property
    def peak_cpus_per_episode(self) -> int:
        return 4 if self.release_source_before_replay else 6

    @property
    def peak_memory_mb_per_episode(self) -> int:
        return 9216 if self.release_source_before_replay else 17408

    def node_capacity(self, node: Node) -> int:
        return min(
            node.cpus // self.peak_cpus_per_episode,
            node.memory_mb // self.peak_memory_mb_per_episode,
        )

    @model_validator(mode="after")
    def validate_contract(self) -> DispatchConfig:
        if self.k not in (2, 3, 4, 6):
            raise ValueError("K must be 2, 3, 4 or 6 in a separate resource-checked arm")
        if self.budget != EpisodeBudget():
            raise ValueError("throughput arms require the registered 100-step/600-second budget")
        if len(set(self.endpoints)) != len(self.endpoints) or any(
            not re.fullmatch(r"http://127\.0\.0\.1:281(?:0[0-9]|10)/v1/?", url)
            for url in self.endpoints
        ):
            raise ValueError("unique registered login-local endpoint forwards required")
        if len({t.key for t in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate tasks would change the denominator")
        if len({n.name for n in self.nodes}) != len(self.nodes):
            raise ValueError("duplicate allocation nodes")
        capacity = sum(self.node_capacity(n) for n in self.nodes)
        if capacity < len(self.endpoints) * self.k:
            raise ValueError("declared CPU/memory allocation cannot support requested concurrency")
        if not self.server_settings:
            raise ValueError("record exact serving-arm settings before measurement")
        for path in [
            self.source_root,
            self.source_manifest,
            self.python,
            *(t.pin for t in self.tasks),
        ]:
            if not path.is_absolute():
                raise ValueError("all execution and pin paths must be absolute")
        return self


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as handle:
        handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def verify_inputs(config: DispatchConfig) -> dict[str, Any]:
    root = config.source_root.resolve(strict=True)
    manifest = json.loads(config.source_manifest.read_bytes())
    entries = manifest["files"]
    paths = []
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe source manifest path")
        path = root / relative
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("source manifest escaped frozen root")
        if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise ValueError("frozen source manifest mismatch")
        paths.append(str(relative))
    if len(set(paths)) != len(paths) or not paths:
        raise ValueError("ambiguous source manifest")
    if "domains/swe_agents/scripts/throughput_dispatch.py" not in paths:
        raise ValueError("dispatcher itself must belong to the frozen source manifest")
    pins = []
    for task in config.tasks:
        value = json.loads(task.pin.read_bytes())
        if value.get("key") != task.key:
            raise ValueError("task identity differs from frozen pin")
        pins.append({**task.model_dump(mode="json"), "sha256": digest(task.pin)})
    return {"source_manifest_sha256": digest(config.source_manifest), "task_pins": pins}


def _slurm_query(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, timeout=10, check=True).stdout


def _remaining_seconds(value: str) -> int | None:
    if value == "UNLIMITED":
        return None
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d{2})(?::(\d{2}))?", value)
    if match is None:
        raise RuntimeError("allocation remaining time is unavailable")
    days, first, second, third = match.groups()
    if int(second) >= 60 or (third is not None and int(third) >= 60):
        raise RuntimeError("invalid allocation remaining time")
    if days is not None and third is None:
        raise RuntimeError("ambiguous allocation remaining time")
    return int(days or 0) * 86400 + (
        int(first) * 3600 + int(second) * 60 + int(third)
        if third is not None
        else int(first) * 60 + int(second)
    )


def cluster_preflight(config: DispatchConfig, query: Any = _slurm_query) -> dict[str, Any]:
    """Read scheduling state only; refuse unhealthy nodes or a short allocation."""
    beginning = time.monotonic()
    allocation = query(["squeue", "-j", config.allocation_id, "-h", "-o", "%i|%T|%L|%N"])
    rows = [line.strip().split("|") for line in allocation.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 4 or rows[0][0] != config.allocation_id:
        raise RuntimeError("allocation is missing or ambiguous")
    identifier, state, remaining_text, expression = rows[0]
    if state != "RUNNING":
        raise RuntimeError("allocation is not RUNNING")
    remaining = _remaining_seconds(remaining_text)
    allocated = set(query(["scontrol", "show", "hostnames", expression]).split())
    selected = {node.name for node in config.nodes}
    if not selected <= allocated:
        raise RuntimeError("selected CPU node is outside the live allocation")
    raw = query(["scontrol", "show", "node", ",".join(sorted(selected)), "--oneliner"])
    states = {}
    for line in raw.splitlines():
        fields = dict(re.findall(r"(?:^|\s)([A-Za-z]+)=(\S+)", line))
        name, node_state = fields.get("NodeName"), fields.get("State", "")
        if name not in selected or name in states:
            raise RuntimeError("node health response differs from selected nodes")
        parts = node_state.split("+")
        if (
            not parts
            or parts[0] not in {"IDLE", "MIXED", "ALLOCATED"}
            or not set(parts[1:]) <= {"DYNAMIC_NORM", "CLOUD"}
        ):
            raise RuntimeError(f"unhealthy selected node {name}: {node_state}")
        states[name] = node_state
    if set(states) != selected:
        raise RuntimeError("selected node health is unavailable")
    required = config.duration_seconds + 120
    checked_remaining = None if remaining is None else remaining - (time.monotonic() - beginning)
    if checked_remaining is not None and checked_remaining < required:
        raise RuntimeError("allocation cannot cover arm duration plus 120-second cleanup reserve")
    return {
        "allocation_id": identifier,
        "allocation_state": state,
        "selected_node_states": states,
        "remaining_seconds_at_check": checked_remaining,
        "unlimited": remaining is None,
        "required_seconds": required,
        "cleanup_reserve_seconds": 120,
    }


def preflight(endpoints: list[str]) -> list[dict[str, Any]]:
    result = []
    for url in endpoints:
        with urllib.request.urlopen(
            url.rstrip("/").removesuffix("/v1") + "/health", timeout=5
        ) as r:
            if r.status != 200:
                raise RuntimeError("replica is not healthy")
        with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=5) as r:
            models = json.load(r)
        if not any(
            m.get("id") == "devstral-base-rate" and m.get("root", "").endswith("/" + MODEL_REVISION)
            for m in models.get("data", [])
        ):
            raise RuntimeError("replica model revision differs from arm registration")
        result.append({"endpoint": url, "models": models})
    return result


def step_name(arm: str, key: str, namespace: str = "") -> str:
    return "thr-" + hashlib.sha256((namespace + ":" + arm + ":" + key).encode()).hexdigest()[:24]


def select_endpoint(loads: list[int], k: int, cursor: int) -> int | None:
    for offset in range(len(loads)):
        index = (cursor + offset) % len(loads)
        if loads[index] < k:
            return index
    return None


def owned_steps(allocation: str, names: set[str]) -> list[str]:
    result = subprocess.run(
        ["squeue", "--steps", "-j", allocation, "-h", "-o", "%i|%j"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    ids = []
    for line in result.stdout.splitlines():
        identifier, separator, name = line.strip().partition("|")
        if (
            separator
            and name in names
            and re.fullmatch(re.escape(allocation) + r"\.[0-9]+", identifier)
        ):
            ids.append(identifier)
    return ids


def cancel_owned(allocation: str, names: set[str]) -> dict[str, Any]:
    ids = owned_steps(allocation, names)
    if ids:
        subprocess.run(["scancel", *ids], capture_output=True, timeout=15, check=True)
    return {"allocation": allocation, "owned_step_names": sorted(names), "cancelled_step_ids": ids}


def summarize(records: list[dict[str, Any]], planned: int, elapsed: float) -> dict[str, Any]:
    counts = dict(
        planned=planned,
        attempted=0,
        episode_completed=0,
        diagnostic_measured=0,
        diagnostic_passed=0,
        diagnostic_failed=0,
        admission_rejected=0,
        unknown=0,
        not_attempted=0,
        budget_exhausted=0,
    )
    durations, first_requests = [], []
    for record in records:
        if record.get("status") == "not_attempted":
            counts["not_attempted"] += 1
            continue
        counts["attempted"] += 1
        episode = record.get("episode", {})
        completed = episode.get("status") == "completed"
        rejected = episode.get("admission_status") == "rejected"
        measured = completed and not rejected and type(episode.get("diagnostic_passed")) is bool
        counts["episode_completed"] += int(completed)
        counts["admission_rejected"] += int(rejected)
        counts["diagnostic_measured"] += int(measured)
        counts["diagnostic_passed"] += int(measured and episode["diagnostic_passed"])
        counts["diagnostic_failed"] += int(measured and not episode["diagnostic_passed"])
        counts["unknown"] += int(not measured and not rejected)
        counts["budget_exhausted"] += int(episode.get("budget_exhausted") is True)
        if isinstance(record.get("elapsed_seconds"), (int, float)):
            durations.append(record["elapsed_seconds"])
        if isinstance(record.get("first_model_request_seconds"), (int, float)):
            first_requests.append(record["first_model_request_seconds"])

    def distribution(values: list[float]) -> dict[str, Any]:
        values = sorted(values)
        return {
            "n": len(values),
            "mean": sum(values) / len(values) if values else None,
            "p50": values[math.ceil(len(values) * 0.5) - 1] if values else None,
            "p95": values[math.ceil(len(values) * 0.95) - 1] if values else None,
        }

    counts["unresolved_total"] = counts["admission_rejected"] + counts["unknown"]
    model_seconds = sum(r.get("model_wall_seconds", 0) for r in records)
    output_tokens = sum(r.get("measured_output_tokens", 0) for r in records)
    hours = elapsed / 3600
    return {
        **counts,
        "elapsed_seconds_including_stagger_and_cleanup": elapsed,
        "completed_episodes_per_hour": counts["episode_completed"] / hours if hours else None,
        "diagnostic_verdicts_per_hour": counts["diagnostic_measured"] / hours if hours else None,
        "model_wall_seconds": model_seconds,
        "measured_output_tokens": output_tokens,
        "aggregate_model_ms_per_output_token": model_seconds * 1000 / output_tokens
        if output_tokens
        else None,
        "episode_wall_seconds": distribution(durations),
        "first_model_request_seconds": distribution(first_requests),
        "protected_status": "unknown",
        "clean_solve_eligible": False,
        "verification_mode": "diagnostic",
    }


def controller(config: DispatchConfig, task: Task, out: Path, name: str) -> None:
    from domains.swe_agents.environment.spec import TaskPin
    from domains.swe_agents.scripts import full_pool_episode as episode

    original = episode.AllocatedRuntime

    class OwnedRuntime(original):
        def argv(self, image: str, workdir: str, python_env: str = "image") -> list[str]:
            return [
                "--job-name=" + name if a.startswith("--job-name=") else a
                for a in super().argv(image, workdir, python_env)
                if a not in {"--overlap", "--exclude=worker-4,worker-5"}
            ]

    episode.AllocatedRuntime = OwnedRuntime

    def interrupted(_signum: int, _frame: Any) -> None:
        raise RuntimeError("throughput arm deadline or interruption")

    signal.signal(signal.SIGTERM, interrupted)
    episode.run_episode(
        TaskPin.model_validate_json(task.pin.read_bytes()),
        out,
        name,
        max_steps=config.budget.max_steps,
        max_seconds=config.budget.max_seconds,
        max_output_tokens=config.budget.max_output_tokens,
        verification_mode="diagnostic",
        release_source_before_replay=config.release_source_before_replay,
    )


def worker(config: DispatchConfig, out: Path, index: int, endpoint: int, node: str) -> None:
    task = config.tasks[index]
    name = step_name(config.arm_id, task.key, str(out))
    command = [
        "srun",
        "--jobid=" + config.allocation_id,
        "--job-name=" + name,
        "--exact",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=2",
        "--mem=1024M",
        "--nodelist=" + node,
        "--cpu-bind=none",
        "env",
        "PYTHONPATH=" + str(config.source_root),
        str(config.python),
        "-u",
        "-m",
        "domains.swe_agents.scripts.throughput_dispatch",
        "--internal",
        "controller",
        "--config",
        str(out / "config.json"),
        "--output",
        str(out),
        "--task-index",
        str(index),
    ]

    def interrupted(_signum: int, _frame: Any) -> None:
        raise RuntimeError("throughput worker interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    run_local_bridge(
        command,
        out / "bridge" / name,
        config.endpoints[endpoint],
        "devstral-base-rate",
        budget=config.budget,
    )


def run_dispatch(config: DispatchConfig, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    for folder in ("bridge", "episodes", "logs", "progress"):
        (out / folder).mkdir()
    save(out / "config.json", config.model_dump(mode="json"))
    bindings = verify_inputs(config)
    health = preflight(config.endpoints)
    try:
        cluster_health = cluster_preflight(config)
    except Exception as exc:
        save(
            out / "preflight-failure.json",
            {"stage": "cluster_health", "error_type": type(exc).__name__, "reason": str(exc)},
        )
        raise
    save(
        out / "registration.json",
        {
            "kind": "cluster_local_throughput_arm_v1",
            "config": config.model_dump(mode="json"),
            **bindings,
            "endpoint_preflight": health,
            "cluster_preflight": cluster_health,
            "model": CANONICAL_MODEL,
            "revision": MODEL_REVISION,
            "verification_mode": "diagnostic",
            "clean_solve_eligible": False,
            "transport": "cluster_local_srun_and_loopback_forward",
            "serving_settings_evidence": "caller-declared; preflight checks model identity",
            "concurrency": len(config.endpoints) * config.k,
            "slurm_resource_policy": {
                "overlap": False,
                "controller_cpus": 2,
                "controller_memory_mb": 1024,
                "broker_cpus": 2,
                "broker_memory_mb": 8192,
                "source_released_before_replay": config.release_source_before_replay,
                "peak_cpus_per_episode": config.peak_cpus_per_episode,
                "peak_memory_mb_per_episode": config.peak_memory_mb_per_episode,
            },
            "owned_step_names": [step_name(config.arm_id, t.key, str(out)) for t in config.tasks],
        },
    )
    started = time.monotonic()
    start_epoch = time.time()
    deadline = started + config.duration_seconds
    active: dict[int, dict[str, Any]] = {}
    records: dict[int, dict[str, Any]] = {}
    loads = [0] * len(config.endpoints)
    node_loads = [0] * len(config.nodes)
    cursor = next_task = 0
    next_start = started
    names: set[str] = set()
    interrupted = False

    def finish(index: int, entry: dict[str, Any], reason: str | None = None) -> None:
        task = config.tasks[index]
        report = {
            "key": task.key,
            "corpus": task.corpus,
            "endpoint": entry["endpoint"],
            "node": config.nodes[entry["node"]].name,
            "started_epoch": entry["epoch"],
            "elapsed_seconds": time.monotonic() - entry["started"],
            "status": "unknown",
        }
        summary = out / "episodes" / entry["name"] / "summary.json"
        if summary.exists():
            report["episode"] = json.loads(summary.read_bytes())
            report["status"] = report["episode"]["status"]
        if reason:
            report["dispatch_reason"] = reason
        requests = sorted((out / "bridge" / entry["name"]).glob("*-original-request.json"))
        if requests:
            report["first_model_request_seconds"] = max(
                0, requests[0].stat().st_mtime - entry["epoch"]
            )
        completions = list((out / "bridge" / entry["name"]).glob("*-completion.json"))
        report["model_calls_with_receipts"] = len(completions)
        report["model_wall_seconds"] = 0.0
        report["measured_output_tokens"] = 0
        for completion_path in completions:
            completion = json.loads(completion_path.read_bytes())
            report["model_wall_seconds"] += completion.get("usage", {}).get("wall_seconds", 0)
            report["measured_output_tokens"] += (
                completion.get("raw", {}).get("usage", {}).get("completion_tokens", 0)
            )
        failure = out / "bridge" / entry["name"] / "failure.json"
        if failure.exists():
            report["bridge_failure"] = json.loads(failure.read_bytes())
        report["worker_exit"] = entry["process"].poll()
        records[index] = report
        save(out / "progress" / (task.key + ".json"), report)
        entry["log"].close()
        loads[entry["endpoint"]] -= 1
        node_loads[entry["node"]] -= 1

    try:
        while active or next_task < len(config.tasks):
            now = time.monotonic()
            for index, entry in list(active.items()):
                if entry["process"].poll() is not None:
                    finish(index, entry)
                    del active[index]
            if now >= deadline:
                interrupted = True
                break
            endpoint = select_endpoint(loads, config.k, cursor)
            available_nodes = [
                i
                for i, n in enumerate(config.nodes)
                if node_loads[i] < config.node_capacity(n)
            ]
            node = min(available_nodes, key=lambda i: node_loads[i]) if available_nodes else None
            if (
                next_task < len(config.tasks)
                and endpoint is not None
                and node is not None
                and now >= next_start
            ):
                index = next_task
                task = config.tasks[index]
                name = step_name(config.arm_id, task.key, str(out))
                names.add(name)
                log = (out / "logs" / (name + ".log")).open("wb")
                argv = [
                    str(config.python),
                    "-u",
                    "-m",
                    "domains.swe_agents.scripts.throughput_dispatch",
                    "--internal",
                    "worker",
                    "--config",
                    str(out / "config.json"),
                    "--output",
                    str(out),
                    "--task-index",
                    str(index),
                    "--endpoint-index",
                    str(endpoint),
                    "--node",
                    config.nodes[node].name,
                ]
                env = {
                    k: os.environ[k]
                    for k in ("PATH", "HOME", "USER", "LANG", "SSH_AUTH_SOCK")
                    if k in os.environ
                }
                env["PYTHONPATH"] = str(config.source_root)
                try:
                    process = subprocess.Popen(
                        argv, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
                    )
                except OSError as exc:
                    log.close()
                    records[index] = {
                        "key": task.key,
                        "corpus": task.corpus,
                        "status": "unknown",
                        "reason": "worker_start_failed",
                        "error_type": type(exc).__name__,
                        "elapsed_seconds": 0,
                    }
                    save(out / "progress" / (task.key + ".json"), records[index])
                    next_task += 1
                    next_start = now + config.stagger_seconds
                    continue
                active[index] = {
                    "process": process,
                    "log": log,
                    "name": name,
                    "endpoint": endpoint,
                    "node": node,
                    "started": now,
                    "epoch": time.time(),
                }
                loads[endpoint] += 1
                node_loads[node] += 1
                cursor = (endpoint + 1) % len(loads)
                next_task += 1
                next_start = now + config.stagger_seconds
                save(
                    out / "progress" / (task.key + ".json"),
                    {
                        "key": task.key,
                        "status": "running",
                        "endpoint": endpoint,
                        "started_epoch": active[index]["epoch"],
                    },
                )
            elif not active and next_task == len(config.tasks):
                break
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    except BaseException:
        interrupted = True
        raise
    finally:
        cleanup: dict[str, Any] = {"needed": bool(active)}
        if names:
            try:
                cleanup.update(cancel_owned(config.allocation_id, names))
            except Exception as exc:
                cleanup["slurm_cleanup_error"] = type(exc).__name__
            for entry in active.values():
                if entry["process"].poll() is None:
                    try:
                        os.killpg(entry["process"].pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            grace = time.monotonic() + 30
            while (
                any(e["process"].poll() is None for e in active.values())
                and time.monotonic() < grace
            ):
                time.sleep(0.1)
            for index, entry in active.items():
                if entry["process"].poll() is None:
                    os.killpg(entry["process"].pid, signal.SIGKILL)
                    entry["process"].wait(timeout=5)
                finish(index, entry, "arm_deadline" if interrupted else "cleanup")
            try:
                remaining = owned_steps(config.allocation_id, names)
                if remaining:
                    subprocess.run(
                        ["scancel", "--signal=KILL", *remaining],
                        capture_output=True,
                        timeout=15,
                        check=True,
                    )
                    time.sleep(1)
                cleanup["remaining_owned_steps"] = owned_steps(config.allocation_id, names)
            except Exception as exc:
                cleanup["cleanup_verification_error"] = type(exc).__name__
        save(out / "cleanup.json", cleanup)
        for index in range(next_task, len(config.tasks)):
            task = config.tasks[index]
            records[index] = {
                "key": task.key,
                "corpus": task.corpus,
                "status": "not_attempted",
                "reason": "arm deadline or interruption",
            }
            save(out / "progress" / (task.key + ".json"), records[index])
        elapsed = time.monotonic() - started
        result = summarize(list(records.values()), len(config.tasks), elapsed)
        result.update(
            arm_id=config.arm_id,
            k=config.k,
            started_epoch=start_epoch,
            ended_epoch=time.time(),
            interrupted=interrupted,
            cleanup_verified=not cleanup.get("remaining_owned_steps")
            and not any(k.endswith("error") for k in cleanup),
        )
        save(out / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--internal", choices=("worker", "controller"))
    parser.add_argument("--task-index", type=int)
    parser.add_argument("--endpoint-index", type=int)
    parser.add_argument("--node")
    args = parser.parse_args()
    config = DispatchConfig.model_validate_json(args.config.read_bytes())
    if args.internal == "controller":
        task = config.tasks[args.task_index]
        name = step_name(config.arm_id, task.key, str(args.output))
        controller(config, task, args.output / "episodes" / name, name)
    elif args.internal == "worker":
        worker(config, args.output, args.task_index, args.endpoint_index, args.node)
    else:

        def interrupted(_signum: int, _frame: Any) -> None:
            raise KeyboardInterrupt("throughput dispatcher interrupted")

        signal.signal(signal.SIGTERM, interrupted)
        print(json.dumps(run_dispatch(config, args.output.resolve())), flush=True)


if __name__ == "__main__":
    main()
