"""Synthetic receipt mutations: no workloads, images, or model calls are executed."""

import copy
import json

import pytest

from domains.swe_agents.environment.generator import TaskPool
from domains.swe_agents.environment.gold import digest
from tests.test_gold_admission import fixture, seal, write

COUNTS = {"discovery_149": 149, "confirm_A": 60, "confirm_B": 60, "recall_uncond": 52}
IID = "org__task-1"


@pytest.fixture(autouse=True)
def isolate_admission_from_execution_provenance(monkeypatch):
    """These unit fixtures assert admission logic; dedicated tests validate provenance."""
    from domains.swe_agents.environment import prun_receipts

    monkeypatch.setattr(prun_receipts, "validate_backend", lambda *args: None, raising=False)


def read(path):
    return json.loads(path.read_text())


def full_fixture(tmp_path):
    root, _ = fixture(tmp_path)
    return root


def update_result(root, result):
    write(root / "evidence" / IID / "result.json", result)
    path = root / "discovery_149/ledger.jsonl"
    ledger = [json.loads(line) for line in path.read_text().splitlines()]
    ledger[0] = result
    path.write_text("".join(json.dumps(r) + "\n" for r in ledger))
    (root / "discovery_149/pins.jsonl").write_text(json.dumps(result["task_pin"]) + "\n")


def admit(root):
    return TaskPool.from_prun_receipt(root, seal(root))


def test_full_fixture_preserves_every_selected_unknown(tmp_path):
    pool = admit(full_fixture(tmp_path))
    assert len(pool.pins) == 1
    assert len(pool.admission_ledger) == 149
    assert list(pool.admission_ledger.values()).count("unknown") == 148


@pytest.mark.parametrize(
    "name",
    ["../outside", "/tmp/absolute", "./candidates.json", "discovery_149/../candidates.json", ""],
)
def test_manifest_rejects_noncanonical_or_escaping_paths(tmp_path, name):
    root = full_fixture(tmp_path)
    seal(root)
    manifest = read(root / "MANIFEST.json")
    entry = copy.deepcopy(next(e for e in manifest["files"] if e["path"] == "candidates.json"))
    entry["path"] = name
    manifest["files"].append(entry)
    write(root / "MANIFEST.json", manifest)
    with pytest.raises(ValueError):
        TaskPool.from_prun_receipt(root, digest(root / "MANIFEST.json"))


def test_manifest_duplicate_entry_rejected(tmp_path):
    root = full_fixture(tmp_path)
    seal(root)
    manifest = read(root / "MANIFEST.json")
    manifest["files"].append(manifest["files"][0])
    write(root / "MANIFEST.json", manifest)
    with pytest.raises(ValueError):
        TaskPool.from_prun_receipt(root, digest(root / "MANIFEST.json"))


@pytest.mark.parametrize("kind", ["missing", "directory", "internal_symlink", "parent_symlink"])
def test_manifest_unreadable_or_symlink_entries_fail_closed(tmp_path, kind):
    root = full_fixture(tmp_path)
    target = root / "payload.txt"
    target.write_text("evidence")
    if kind == "internal_symlink":
        target.unlink()
        target.symlink_to("candidates.json")
    elif kind == "parent_symlink":
        (root / "linked").symlink_to("discovery_149", target_is_directory=True)
    anchor = seal(root)
    if kind == "parent_symlink":
        manifest = read(root / "MANIFEST.json")
        payload = root / "linked/ledger.jsonl"
        manifest["files"].append(
            {
                "path": "linked/ledger.jsonl",
                "size": payload.stat().st_size,
                "sha256": digest(payload),
            }
        )
        write(root / "MANIFEST.json", manifest)
        anchor = digest(root / "MANIFEST.json")
    elif kind in {"missing", "directory"}:
        target.unlink()
        if kind == "directory":
            target.mkdir()
    with pytest.raises(ValueError):
        TaskPool.from_prun_receipt(root, anchor)


@pytest.mark.parametrize(
    "mutation",
    [
        "remove_both",
        "duplicate_candidate",
        "duplicate_ledger",
        "other_corpus_ledger",
        "unknown_corpus",
    ],
)
def test_frozen_denominators_cannot_be_reduced_or_duplicated(tmp_path, mutation):
    root = full_fixture(tmp_path)
    rows = read(root / "candidates.json")
    path = root / "confirm_A/ledger.jsonl"
    ledger = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "remove_both":
        removed = ledger.pop()["instance_id"]
        rows = [r for r in rows if r["instance_id"] != removed]
    elif mutation == "duplicate_candidate":
        rows.append(rows[-1])
    elif mutation == "duplicate_ledger":
        ledger.append(ledger[0])
    elif mutation == "other_corpus_ledger":
        ledger.pop()
    else:
        rows[-1]["corpus"] = "unregistered"
    write(root / "candidates.json", rows)
    path.write_text("".join(json.dumps(r) + "\n" for r in ledger))
    with pytest.raises(ValueError):
        admit(root)


def canonical_fixture(tmp_path):
    root = full_fixture(tmp_path)
    rows = read(root / "candidates.json")
    canonical = rows[0]["FAIL_TO_PASS"][0]
    raw = "test_fix[param"
    rows[0]["FAIL_TO_PASS"] = [raw]
    write(root / "candidates.json", rows)
    result = read(root / "evidence" / IID / "result.json")
    result["canonical_expected"] = {"FAIL_TO_PASS": [canonical], "PASS_TO_PASS": ["test_kept"]}
    result["canonical_statuses"] = [p["statuses"] for p in result["phases"]]
    result["source_identifier_audit"] = {"mapping": {raw: canonical}}
    result["contract_audit"] = {
        "valid": True,
        "reason": "all expected transitions and process exits match",
        "baseline_statuses": result["phases"][0]["statuses"],
        "gold_statuses": result["phases"][1]["statuses"],
    }
    for arm in ("baseline", "gold"):
        write(root / "evidence" / IID / arm / "input/task.json", rows[0])
    update_result(root, result)
    return root


def test_unique_identifier_completion_admits_literal_pin(tmp_path):
    pool = admit(canonical_fixture(tmp_path))
    assert pool.pins[0].fail_to_pass == ("test_fix[param with spaces]",)


@pytest.mark.parametrize(
    "mutation",
    [
        "swap",
        "collision",
        "ambiguous",
        "one_arm_only",
        "raw_contradiction",
        "forged_mapping",
        "spurious_mapping",
    ],
)
def test_canonical_metadata_cannot_override_literal_raw_evidence(tmp_path, mutation):
    root = canonical_fixture(tmp_path)
    result = read(root / "evidence" / IID / "result.json")
    directory = root / "evidence" / IID
    if mutation == "swap":
        result["canonical_expected"] = {
            "FAIL_TO_PASS": ["test_kept"],
            "PASS_TO_PASS": ["test_fix[param with spaces]"],
        }
        result["task_pin"].update(
            fail_to_pass=["test_kept"], pass_to_pass=["test_fix[param with spaces]"]
        )
    elif mutation == "collision":
        result["canonical_expected"]["PASS_TO_PASS"] = ["test_fix[param with spaces]"]
        result["task_pin"]["pass_to_pass"] = ["test_fix[param with spaces]"]
    elif mutation == "ambiguous":
        for arm in ("baseline", "gold"):
            path = directory / arm / "output/test.log"
            path.write_text(path.read_text() + "PASSED test_fix[param another]\n")
    elif mutation == "one_arm_only":
        path = directory / "baseline/output/test.log"
        path.write_text("FAILED test_fix[param alternate]\nPASSED test_kept\n")
    elif mutation == "forged_mapping":
        result["source_identifier_audit"]["mapping"] = {"test_fix[param": "test_kept"}
    elif mutation == "spurious_mapping":
        result["source_identifier_audit"]["mapping"]["unrelated[raw"] = "test_kept"
    else:
        path = directory / "gold/output/test.log"
        path.write_text(path.read_text() + "FAILED test_fix[param with spaces] - contradiction\n")
    update_result(root, result)
    with pytest.raises(ValueError):
        admit(root)


def named_fixture(tmp_path, monkeypatch):
    """Exercise provenance policy with explicit synthetic producer hashes, never execute them."""
    from domains.swe_agents.environment import prun_provenance as backend

    root = full_fixture(tmp_path)
    row = read(root / "candidates.json")[0]
    result = read(root / "evidence" / IID / "result.json")
    controller = "gold_verify_pyxis_ram_resume_prun.py"
    scripts = {}
    for name in [controller, "pyxis_gold_runner.py", "gold_verify_prun.py", "ram_root_prun.py"]:
        (root / name).write_text("Synthetic test producer; never executed: " + name)
        scripts[name] = digest(root / name)
    monkeypatch.setattr(backend, "CONTROLLERS", {controller: scripts[controller]})
    for constant, filename in [
        ("RUNNER", "pyxis_gold_runner.py"),
        ("COMMON", "gold_verify_prun.py"),
        ("HELPER", "ram_root_prun.py"),
    ]:
        monkeypatch.setattr(backend, constant, scripts[filename])
    write(
        root / "registration.json",
        {"scripts": scripts, "job_id": "123", "allocated_nodes": "worker-test"},
    )
    for moment in ("before", "after"):
        result["image_hash_" + moment] = {"exit": 0, "timeout": False}
        (root / "evidence" / IID / f"image-hash-{moment}.log").write_text(
            result["image_sha256"] + "  " + row["image_path"] + "\n"
        )
    import hashlib

    for arm, phase in zip(("baseline", "gold"), result["phases"], strict=True):
        name = "prun_123_" + hashlib.sha256(IID.encode()).hexdigest()[:16] + "_" + arm
        dest = f"/home/guests/andrei/va/data/tasks/{root.name}/evidence/{IID}/{arm}"
        argv = [
            "srun",
            "--jobid=123",
            "--exclusive",
            "--exact",
            "--input=none",
            "--nodes=1",
            "--ntasks=1",
            "--cpus-per-task=4",
            "--mem=24G",
            "--cpu-bind=none",
            "--container-name=" + name,
            "--container-writable",
            "--container-remap-root",
            "--no-container-mount-home",
            "--no-container-entrypoint",
            "--container-workdir=/",
            "--container-mounts="
            + dest
            + "/input:/va-prun-input:ro,"
            + dest
            + "/output:/va-prun-output",
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            "set -e; exec python /va-prun-input/runner.py " + arm,
        ]
        directory = root / "evidence" / IID / arm
        write(
            directory / "command.json",
            {"argv": argv, "rootfs_name": name, "scratch_parent": f"/mnt/memory/{root.name}/data"},
        )
        (directory / "input/runner.py").write_bytes((root / "pyxis_gold_runner.py").read_bytes())
        (directory / "build.log").write_text("[INFO] Extracting squashfs filesystem...\ntmpfs\n")
        phase.update(
            node="worker-test",
            build={"exit": 0, "timeout": False},
            cleanup={"exit": 0, "timeout": False},
        )
    update_result(root, result)
    return root, row, result


def test_named_backend_synthetic_policy_positive(tmp_path, monkeypatch):
    from domains.swe_agents.environment.prun_integrity import Receipt
    from domains.swe_agents.environment.prun_provenance import validate_backend

    root, row, result = named_fixture(tmp_path, monkeypatch)
    validate_backend(Receipt(root, seal(root)), row, result)


@pytest.mark.parametrize(
    "mutation",
    [
        "reuse_arm",
        "scratch",
        "hash_locator",
        "build_exit",
        "cleanup_timeout",
        "missing_extraction",
        "runner",
        "producer",
    ],
)
def test_named_backend_rejects_invalid_preparation_and_arm_binding(tmp_path, monkeypatch, mutation):
    from domains.swe_agents.environment.prun_integrity import Receipt
    from domains.swe_agents.environment.prun_provenance import validate_backend

    root, row, result = named_fixture(tmp_path, monkeypatch)
    directory = root / "evidence" / IID / "gold"
    command = read(directory / "command.json")
    if mutation == "reuse_arm":
        baseline = read(root / "evidence" / IID / "baseline/command.json")
        command["rootfs_name"] = baseline["rootfs_name"]
        command["argv"] = [arg.replace("_gold", "_baseline") for arg in command["argv"]]
    elif mutation == "scratch":
        command["scratch_parent"] = "/mnt/memory/other-run/data"
    elif mutation == "hash_locator":
        (directory.parent / "image-hash-before.log").write_text(
            result["image_sha256"] + "  /wrong/image.sqsh\n"
        )
    elif mutation == "build_exit":
        result["phases"][1]["build"]["exit"] = 1
    elif mutation == "cleanup_timeout":
        result["phases"][1]["cleanup"]["timeout"] = True
    elif mutation == "missing_extraction":
        (directory / "build.log").write_text("tmpfs\n")
    elif mutation == "runner":
        (directory / "input/runner.py").write_text("different producer")
    else:
        (root / "ram_root_prun.py").write_text("different producer")
    write(directory / "command.json", command)
    update_result(root, result)
    with pytest.raises(ValueError):
        validate_backend(Receipt(root, seal(root)), row, result)


@pytest.mark.parametrize("mutation", ["alter_raw", "omit_step_log", "omit_cleanup_log"])
def test_descendant_cannot_reseal_changed_or_missing_original_execution(
    tmp_path, monkeypatch, mutation
):
    import shutil

    from domains.swe_agents.environment.prun_integrity import Receipt
    from domains.swe_agents.environment.prun_provenance import validate_backend

    origin, row, result = named_fixture(tmp_path, monkeypatch)
    for arm in ("baseline", "gold"):
        for log in ("step.log", "cleanup.log"):
            (origin / "evidence" / IID / arm / log).write_text("synthetic recorded output\n")
    anchor = seal(origin)
    descendant = tmp_path / "derived"
    shutil.copytree(origin, descendant)
    write(
        descendant / "registration.json",
        {"parent_run": origin.name, "parent_manifest_sha256": anchor},
    )
    shutil.copyfile(
        descendant / "evidence" / IID / "result.json",
        descendant / "evidence" / IID / "original-result.json",
    )
    # A valid descendant is accepted before the independently re-sealed mutation.
    validate_backend(Receipt(descendant, seal(descendant)), row, result)
    if mutation == "alter_raw":
        path = descendant / "evidence" / IID / "gold/output/test.log"
        path.write_text(path.read_text() + "PASSED extra_test\n")
    else:
        log = "step.log" if mutation == "omit_step_log" else "cleanup.log"
        (descendant / "evidence" / IID / "gold" / log).unlink()
    with pytest.raises(ValueError):
        validate_backend(Receipt(descendant, seal(descendant)), row, result)
