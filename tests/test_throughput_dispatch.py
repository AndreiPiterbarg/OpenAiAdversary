"""No cluster or model calls: scheduling, denominators, and ownership boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.swe_agents.scripts import throughput_dispatch as dispatch


def config(tmp_path, **updates):
    values = dict(
        arm_id="graph-k3",
        allocation_id="123",
        k=3,
        nodes=[
            dict(name="worker-12", cpus=96, memory_mb=393216),
            dict(name="worker-17", cpus=96, memory_mb=393216),
        ],
        endpoints=["http://127.0.0.1:28100/v1", "http://127.0.0.1:28101/v1"],
        tasks=[
            dict(key=f"task-{i}", pin=str(tmp_path / f"pin-{i}.json"), corpus="same-mix")
            for i in range(8)
        ],
        source_root=str(tmp_path),
        source_manifest=str(tmp_path / "SOURCE_MANIFEST.json"),
        python="/usr/bin/python3",
        duration_seconds=30,
        stagger_seconds=0,
        server_settings={"enforce_eager": False, "max_num_seqs": 16},
    )
    values.update(updates)
    return dispatch.DispatchConfig.model_validate(values)


def test_k6_capacity_and_explicit_arm_validation(tmp_path):
    assert config(tmp_path, k=6).k == 6
    with pytest.raises(ValueError, match="K must"):
        config(tmp_path, k=5)
    with pytest.raises(ValueError, match="cannot support"):
        config(tmp_path, nodes=[dict(name="worker-12", cpus=4, memory_mb=16384)])
    with pytest.raises(ValueError, match="100-step"):
        config(tmp_path, budget={"max_steps": 50})


def test_round_robin_respects_each_endpoint_capacity():
    assert dispatch.select_endpoint([0, 0], 3, 1) == 1
    assert dispatch.select_endpoint([3, 2], 3, 0) == 1
    assert dispatch.select_endpoint([3, 3], 3, 0) is None


def test_serial_source_handoff_is_required_for_48_slots(tmp_path):
    endpoints = [f"http://127.0.0.1:{28100 + i}/v1" for i in range(8)]
    with pytest.raises(ValueError, match="cannot support"):
        config(tmp_path, k=6, endpoints=endpoints)
    serial = config(tmp_path, k=6, endpoints=endpoints, release_source_before_replay=True)
    assert sum(serial.node_capacity(node) for node in serial.nodes) == 48
    assert serial.peak_cpus_per_episode == 4
    assert serial.peak_memory_mb_per_episode == 9216
    with pytest.raises(ValueError, match="cannot support"):
        config(
            tmp_path, k=6, endpoints=endpoints, release_source_before_replay=True,
            nodes=[dict(name="worker-12", cpus=96, memory_mb=393216)],
        )
    with pytest.raises(ValueError, match="cannot support"):
        config(
            tmp_path, k=6, endpoints=endpoints, release_source_before_replay=True,
            nodes=[dict(name="worker-12", cpus=192, memory_mb=9216 * 47)],
        )


def test_handoff_registration_matches_admission(tmp_path, monkeypatch):
    fake_runtime(monkeypatch, tmp_path, lifetime=2)
    settings = config(tmp_path, release_source_before_replay=True)
    dispatch.run_dispatch(settings, tmp_path / "serial")
    policy = json.loads((tmp_path / "serial/registration.json").read_text())["slurm_resource_policy"]
    assert policy["controller_cpus"] == policy["broker_cpus"] == 2
    assert policy["source_released_before_replay"] is True
    assert policy["peak_cpus_per_episode"] == 4
    assert policy["peak_memory_mb_per_episode"] == 9216
    assert policy["overlap"] is False


def test_rejection_unknown_and_budget_censoring_stay_separate():
    records = [
        {"episode": {"status": "completed", "diagnostic_passed": True, "budget_exhausted": True}},
        {"episode": {"status": "completed", "diagnostic_passed": False}},
        {"episode": {"status": "completed", "admission_status": "rejected"}},
        {"episode": {"status": "unknown"}},
        {"status": "not_attempted"},
    ]
    result = dispatch.summarize(records, 5, 3600)
    assert result["episode_completed"] == result["completed_episodes_per_hour"] == 3
    assert result["diagnostic_measured"] == result["diagnostic_verdicts_per_hour"] == 2
    assert result["admission_rejected"] == result["unknown"] == result["not_attempted"] == 1
    assert result["unresolved_total"] == 2 and result["budget_exhausted"] == 1
    assert not result["clean_solve_eligible"]


def test_cleanup_only_exact_owned_steps_and_allocation(monkeypatch):
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout="123.1|ours\n123.2|other\n123.batch|ours\n124.1|ours\n")

    monkeypatch.setattr(dispatch.subprocess, "run", command)
    assert dispatch.cancel_owned("123", {"ours"})["cancelled_step_ids"] == ["123.1"]
    assert calls[-1] == ["scancel", "123.1"]
    assert dispatch.step_name("arm", "task", "/run1") != dispatch.step_name("arm", "task", "/run2")


def fake_runtime(monkeypatch, tmp_path, lifetime):
    clock = [1000.0]
    processes, launches, cleanup_calls = [], [], []
    monkeypatch.setattr(dispatch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dispatch.time, "time", lambda: clock[0] + 10000)
    monkeypatch.setattr(
        dispatch.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    monkeypatch.setattr(
        dispatch, "verify_inputs", lambda config: {"source_manifest_sha256": "fixed"}
    )
    monkeypatch.setattr(dispatch, "preflight", lambda urls: [])
    monkeypatch.setattr(dispatch, "cluster_preflight", lambda config: {"healthy": True})
    monkeypatch.setattr(
        dispatch,
        "cancel_owned",
        lambda allocation, names: cleanup_calls.append(set(names)) or {"cancelled_step_ids": []},
    )
    monkeypatch.setattr(dispatch, "owned_steps", lambda *args: [])

    class Process:
        def __init__(self, argv, **kwargs):
            self.index = int(argv[argv.index("--task-index") + 1])
            self.endpoint = int(argv[argv.index("--endpoint-index") + 1])
            self.node = argv[argv.index("--node") + 1]
            self.out = Path(argv[argv.index("--output") + 1])
            self.started = clock[0]
            self.returncode = None
            self.pid = 9000 + len(processes)
            processes.append(self)
            launches.append((clock[0], self.endpoint, self.node))

        def poll(self):
            if self.returncode is None and clock[0] - self.started >= lifetime:
                self.returncode = 0
                name = dispatch.step_name("graph-k3", f"task-{self.index}", str(self.out))
                path = self.out / "episodes" / name
                path.mkdir()
                (path / "summary.json").write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "diagnostic_passed": True,
                            "budget_exhausted": False,
                        }
                    )
                )
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    def kill(pid, sig):
        next(p for p in processes if p.pid == pid).returncode = -sig

    monkeypatch.setattr(dispatch.subprocess, "Popen", Process)
    monkeypatch.setattr(dispatch.os, "killpg", kill)
    return launches, cleanup_calls


def test_complete_waves_balance_nodes_and_verify_cleanup_even_when_no_active(tmp_path, monkeypatch):
    launches, cleanup_calls = fake_runtime(monkeypatch, tmp_path, lifetime=2)
    result = dispatch.run_dispatch(config(tmp_path), tmp_path / "out")
    assert result["diagnostic_measured"] == 8 and result["cleanup_verified"]
    assert [x[1] for x in launches[:6]] == [0, 1, 0, 1, 0, 1]
    assert [x[2] for x in launches[:6]] == ["worker-12", "worker-17"] * 3
    assert len(cleanup_calls) == 1 and len(cleanup_calls[0]) == 8


def test_global_stagger_applies_to_every_start_and_deadline_retains_denominator(
    tmp_path, monkeypatch
):
    launches, cleanup_calls = fake_runtime(monkeypatch, tmp_path, lifetime=100)
    result = dispatch.run_dispatch(
        config(tmp_path, duration_seconds=10, stagger_seconds=3), tmp_path / "out"
    )
    assert len(launches) == 4
    assert all(b[0] - a[0] >= 3 for a, b in zip(launches, launches[1:], strict=False))
    assert result["attempted"] == result["unknown"] == 4
    assert result["not_attempted"] == 4 and result["planned"] == 8
    assert cleanup_calls and result["cleanup_verified"] and result["interrupted"]


def test_eight_replica_k4_fits_but_k6_refuses_existing_allocation(tmp_path):
    endpoints = [f"http://127.0.0.1:{28100 + i}/v1" for i in range(8)]
    assert config(tmp_path, endpoints=endpoints, k=4).k == 4
    with pytest.raises(ValueError, match="cannot support"):
        config(tmp_path, endpoints=endpoints, k=6)
    nodes = [dict(name=name, cpus=144, memory_mb=417792) for name in ("worker-12", "worker-17")]
    assert config(tmp_path, endpoints=endpoints, nodes=nodes, k=6).k == 6


def test_outer_controller_requests_one_exclusive_cpu(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(dispatch, "run_local_bridge", lambda argv, *a, **kw: commands.append(argv))
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a: None)
    dispatch.worker(config(tmp_path), tmp_path, 0, 0, "worker-12")
    argv = commands[0]
    assert "--overlap" not in argv and "--exact" in argv
    assert "--cpus-per-task=2" in argv and "--mem=1024M" in argv


@pytest.mark.parametrize("release_source", [False, True])
def test_source_and_fresh_runtime_remove_overlap_retain_two_cpu_grants(
    tmp_path, monkeypatch, release_source
):
    from domains.swe_agents.scripts import full_pool_episode as episode
    from tests.test_domain_swe import pin

    settings = config(tmp_path, release_source_before_replay=release_source)
    settings.tasks[0].pin.write_text(pin("task-0", "repo").model_dump_json())
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURMD_NODENAME", "worker-12")
    monkeypatch.setattr(dispatch.signal, "signal", lambda *a: None)
    monkeypatch.setattr(episode, "AllocatedRuntime", episode.AllocatedRuntime)
    calls = []

    def run(*args, **kwargs):
        assert kwargs["release_source_before_replay"] is release_source
        runtime = episode.AllocatedRuntime(cpus=2, memory_mb=8192)
        calls.extend([runtime.argv("/image.sqsh", "/repo"), runtime.argv("/image.sqsh", "/repo")])

    monkeypatch.setattr(episode, "run_episode", run)
    dispatch.controller(settings, settings.tasks[0], tmp_path / "episode", "owned")
    for argv in calls:
        assert "--overlap" not in argv
        assert "--exclude=worker-4,worker-5" not in argv
        assert "--exact" in argv and "--nodelist=worker-12" in argv
        assert "--cpus-per-task=2" in argv and "--mem=8192M" in argv
        assert "--job-name=owned" in argv


@pytest.mark.parametrize(
    "state", ["MIXED+DRAIN+DYNAMIC_NORM", "DOWN", "ALLOCATED+FAIL", "MIXED+NOT_RESPONDING"]
)
def test_unhealthy_selected_nodes_refuse_before_workers(tmp_path, state):
    settings = config(tmp_path, nodes=[dict(name="worker-12", cpus=96, memory_mb=393216)])
    replies = iter(
        [
            "123|RUNNING|00:35:00|worker-12\n",
            "worker-12\n",
            "NodeName=worker-12 State=" + state + " CPUAlloc=0\n",
        ]
    )
    with pytest.raises(RuntimeError, match="unhealthy selected node"):
        dispatch.cluster_preflight(settings, query=lambda argv: next(replies))


def test_healthy_dynamic_node_and_remaining_window_are_attested(tmp_path):
    settings = config(tmp_path, k=2, nodes=[dict(name="worker-12", cpus=96, memory_mb=393216)])
    replies = iter(
        [
            "123|RUNNING|35:00|worker-12\n",
            "worker-12\n",
            "NodeName=worker-12 State=MIXED+DYNAMIC_NORM CPUAlloc=0\n",
        ]
    )
    evidence = dispatch.cluster_preflight(settings, query=lambda argv: next(replies))
    assert evidence["selected_node_states"] == {"worker-12": "MIXED+DYNAMIC_NORM"}
    assert evidence["required_seconds"] == settings.duration_seconds + 120
    assert evidence["remaining_seconds_at_check"] > 2000


@pytest.mark.parametrize("state,timeleft", [("PENDING", "35:00"), ("RUNNING", "00:01:00")])
def test_missing_runtime_or_short_remaining_window_refuses(tmp_path, state, timeleft):
    settings = config(tmp_path, nodes=[dict(name="worker-12", cpus=96, memory_mb=393216)])
    replies = iter(
        [
            f"123|{state}|{timeleft}|worker-12\n",
            "worker-12\n",
            "NodeName=worker-12 State=MIXED+DYNAMIC_NORM\n",
        ]
    )
    with pytest.raises(RuntimeError):
        dispatch.cluster_preflight(settings, query=lambda argv: next(replies))


def test_slurm_allocated_gpu_named_hosts_are_not_hardcoded_out(tmp_path):
    nodes = [dict(name=name, cpus=96, memory_mb=393216) for name in ("worker-4", "worker-5")]
    settings = config(tmp_path, nodes=nodes)
    replies = iter(
        [
            "123|RUNNING|35:00|worker-[4-5]\n",
            "worker-4\nworker-5\n",
            "NodeName=worker-4 State=MIXED+DYNAMIC_NORM\n"
            "NodeName=worker-5 State=ALLOCATED+DYNAMIC_NORM\n",
        ]
    )
    evidence = dispatch.cluster_preflight(settings, query=lambda argv: next(replies))
    assert set(evidence["selected_node_states"]) == {"worker-4", "worker-5"}
