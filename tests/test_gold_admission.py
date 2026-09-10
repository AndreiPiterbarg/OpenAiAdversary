"""P-RUN receipt consumption only: these tests never launch gold workloads."""

import json

import pytest

from adversary.core.manifest import build_manifest
from domains.swe_agents.environment.generator import TaskPool
from domains.swe_agents.environment.gold import digest, expected_results


@pytest.fixture(autouse=True)
def isolate_admission_from_execution_provenance(monkeypatch):
    """These unit fixtures assert admission logic; dedicated tests validate provenance."""
    from domains.swe_agents.environment import prun_receipts

    monkeypatch.setattr(prun_receipts, "validate_backend", lambda *args: None, raising=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def seal(root):
    build_manifest(root).write(root)
    return digest(root / "MANIFEST.json")


def fixture(tmp_path, schema="v2"):
    root = tmp_path / "receipt"
    root.mkdir()
    image = tmp_path / "image.sqsh"
    image.write_bytes(b"immutable image")
    sha = digest(image)
    iid = "org__task-1"
    row = {
        "instance_id": iid,
        "corpus": "discovery_149",
        "repo": "org/task",
        "base_commit": "a" * 40,
        "problem_statement": "fix",
        "schema": schema,
        "image_path": str(image),
        "patch": "gold diff",
        "test_patch": "test diff",
        "test_cmd": "pytest -rA",
        "FAIL_TO_PASS": ["test_fix[param with spaces]"],
        "PASS_TO_PASS": ["test_kept"],
    }
    pin = {
        "key": iid,
        "repo": row["repo"],
        "url": "https://github.com/org/task",
        "commit": row["base_commit"],
        "issue": "fix",
        "test_command": row["test_cmd"],
        "fail_to_pass": row["FAIL_TO_PASS"],
        "pass_to_pass": row["PASS_TO_PASS"],
        "gold_patch": row["patch"],
        "image": "sha256:" + sha,
        "properties": {},
    }
    phases = []
    for arm in ["baseline", "gold"]:
        code = 1 if arm == "baseline" else 0
        status = "FAILED" if code else "PASSED"
        inside = {
            "phase": arm,
            "setup": {"exit": 0},
            "head": row["base_commit"],
            "repo_path": "/testbed" if schema == "v1" else "/task",
            "test": {"exit": code},
        }
        phase = {
            **inside,
            "step": {"exit": 0, "timeout": False},
            "statuses": {row["FAIL_TO_PASS"][0]: status, "test_kept": "PASSED"},
        }
        phases.append(phase)
        directory = root / "evidence" / iid / arm
        write(directory / "output/inside.json", inside)
        write(directory / "input/task.json", row)
        (directory / "input/test.patch").write_text(row["test_patch"])
        (directory / "input/gold.patch").write_text(row["patch"])
        (directory / "output/test.log").write_text(
            status + " test_fix[param with spaces]\nPASSED test_kept\n"
        )
        write(directory / "command.json", {"argv": ["srun", "--container-image=" + str(image)]})
    result = {
        "instance_id": iid,
        "corpus": "discovery_149",
        "status": "verified",
        "valid": True,
        "attempted": True,
        "image_sha256": sha,
        "task_pin": pin,
        "phases": phases,
    }
    write(root / "evidence" / iid / "result.json", result)
    unknown = {
        "instance_id": "other__task-2",
        "corpus": "discovery_149",
        "valid": None,
        "status": "not_selected_smoke",
    }
    candidates = [row]
    for corpus, count in {
        "discovery_149": 149,
        "confirm_A": 60,
        "confirm_B": 60,
        "recall_uncond": 52,
    }.items():
        ledger = [result] if corpus == "discovery_149" else []
        for index in range(count - len(ledger)):
            iid = (
                unknown["instance_id"]
                if corpus == "discovery_149" and index == 0
                else f"{corpus}__unknown-{index}"
            )
            candidates.append(
                {**row, "instance_id": iid, "corpus": corpus, "repo": "synthetic/" + iid}
            )
            ledger.append({**unknown, "instance_id": iid, "corpus": corpus})
        directory = root / corpus
        directory.mkdir()
        (directory / "ledger.jsonl").write_text("".join(json.dumps(item) + "\n" for item in ledger))
        (directory / "pins.jsonl").write_text(
            json.dumps(pin) + "\n" if corpus == "discovery_149" else ""
        )
    write(root / "candidates.json", candidates)
    return root, seal(root)


@pytest.mark.parametrize(
    "schema,workdir,env", [("v1", "/testbed", "conda_testbed"), ("v2", "/task", "image")]
)
def test_verified_pin_resolves_image_and_keeps_unknowns(tmp_path, schema, workdir, env):
    root, anchor = fixture(tmp_path, schema)
    pool = TaskPool.from_prun_receipt(root, anchor)
    assert len(pool.pins) == 1
    pin = pool.pins[0]
    assert pin.image == str(tmp_path / "image.sqsh")
    assert pin.image_sha256 == digest(tmp_path / "image.sqsh")
    assert pin.verification_receipt == anchor
    assert pin.test_patch == "test diff"
    assert (pin.workdir, pin.python_env) == (workdir, env)
    assert len(pool.admission_ledger) == 149
    assert pool.admission_ledger["org__task-1"] == "verified"
    assert pool.admission_ledger["other__task-2"] == "unknown"
    assert list(pool.admission_ledger.values()).count("unknown") == 148


@pytest.mark.parametrize(
    "path",
    ["candidates.json", "discovery_149/pins.jsonl", "evidence/org__task-1/gold/output/test.log"],
)
def test_tampering_rejected_before_use(tmp_path, path):
    root, anchor = fixture(tmp_path)
    (root / path).write_text("changed")
    with pytest.raises(ValueError, match="manifest"):
        TaskPool.from_prun_receipt(root, anchor)


def test_current_image_is_rehashed(tmp_path):
    root, anchor = fixture(tmp_path)
    (tmp_path / "image.sqsh").write_bytes(b"changed")
    with pytest.raises(ValueError, match="image missing or changed"):
        TaskPool.from_prun_receipt(root, anchor)


def test_status_claims_must_match_raw_logs_even_with_valid_manifest(tmp_path):
    root, _ = fixture(tmp_path)
    (root / "evidence/org__task-1/gold/output/test.log").write_text("PASSED test_kept\n")
    with pytest.raises(ValueError, match="missing or conflicting"):
        TaskPool.from_prun_receipt(root, seal(root))


def test_patch_source_mismatch_rejected(tmp_path):
    root, _ = fixture(tmp_path)
    (root / "evidence/org__task-1/gold/input/test.patch").write_text("different diff")
    with pytest.raises(ValueError, match="patch differs"):
        TaskPool.from_prun_receipt(root, seal(root))


def test_external_anchor_is_required(tmp_path):
    root, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="root manifest"):
        TaskPool.from_prun_receipt(root, "0" * 64)


def test_unknown_only_pool_is_empty_not_fabricated(tmp_path):
    root, _ = fixture(tmp_path)
    ledger = root / "discovery_149/ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[0].update(valid=None, status="runtime_error")
    rows[0].pop("task_pin")
    write(root / "evidence/org__task-1/result.json", rows[0])
    ledger.write_text("\n".join(json.dumps(r) for r in rows))
    (root / "discovery_149/pins.jsonl").write_text("")
    pool = TaskPool.from_prun_receipt(root, seal(root))
    assert pool.pins == ()
    assert set(pool.admission_ledger.values()) == {"unknown"}


def test_literal_test_identifiers_and_conflicting_records():
    node = "test_fix[param with spaces]"
    evidence = expected_results(1, "FAILED " + node + " - detail\nPASSED " + node, (node,))
    assert evidence.conflicts == (node,)
    assert not expected_results(0, "PASSED prefix_" + node, (node,)).statuses
