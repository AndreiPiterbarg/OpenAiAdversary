"""Read P-RUN's completed Pyxis receipts; never schedule or repeat its gold jobs."""

import re
from pathlib import Path

from domains.swe_agents.environment.gold import digest
from domains.swe_agents.environment.prun_contract import PhaseEvidence, verify_gold
from domains.swe_agents.environment.prun_identifiers import canonicalize
from domains.swe_agents.environment.prun_integrity import Receipt, strict_json
from domains.swe_agents.environment.prun_provenance import validate_backend
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.environment.test_results import TestStatus


def load_prun_receipt(
    root: Path,
    expected_manifest_sha256: str,
    corpus: str,
) -> tuple[tuple[TaskPin, ...], dict[str, str]]:
    """Require an externally trusted root-manifest digest and validate every consumed file.

    Output retains unknown/invalid rows. Image locators come from authenticated source rows,
    not from interpreting a digest as a filesystem path. No receipt is a cryptographic proof
    of execution: the supplied digest must originate from a trusted producer/run record.
    """
    receipt = Receipt(root, expected_manifest_sha256)
    read, obj = receipt.read, receipt.obj

    if corpus not in {"discovery_149", "confirm_A", "confirm_B", "recall_uncond"}:
        raise ValueError("unknown frozen corpus")
    candidates = obj("candidates.json")
    if len({r["instance_id"] for r in candidates}) != len(candidates):
        raise ValueError("duplicate candidate IDs")
    if len({r["repo"].casefold() for r in candidates}) != len(candidates):
        raise ValueError("candidate repositories must be disjoint")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", r["instance_id"]) for r in candidates):
        raise ValueError("invalid candidate identity")
    sizes = {"discovery_149": 149, "confirm_A": 60, "confirm_B": 60, "recall_uncond": 52}
    if len(candidates) != 321 or any(r["corpus"] not in sizes for r in candidates):
        raise ValueError("frozen candidates must cover all 321 tasks")
    ledgers = {}
    for name, size in sizes.items():
        selected_rows = {r["instance_id"]: r for r in candidates if r["corpus"] == name}
        if len(selected_rows) != size:
            raise ValueError("frozen corpus count differs: " + name)
        rows = [strict_json(line) for line in read(name + "/ledger.jsonl").splitlines() if line]
        if len(rows) != size or {r["instance_id"] for r in rows} != set(selected_rows):
            raise ValueError("ledger does not cover every candidate exactly once")
        for r in rows:
            iid = r["instance_id"]
            if (
                not re.fullmatch(r"[A-Za-z0-9_.-]+", iid)
                or r["corpus"] != name
                or not (r["valid"] is True or r["valid"] is False or r["valid"] is None)
            ):
                raise ValueError("invalid ledger identity or outcome")
            result_name = "evidence/" + iid + "/result.json"
            if result_name in receipt.entries and obj(result_name) != r:
                raise ValueError("per-task result differs from ledger")
            if r["valid"] is not True and "task_pin" in r:
                raise ValueError("unverified row publishes a pin")
        published = [strict_json(line) for line in read(name + "/pins.jsonl").splitlines() if line]
        verified = [r["task_pin"] for r in rows if r["valid"] is True]
        if sorted(published, key=lambda p: p["key"]) != sorted(verified, key=lambda p: p["key"]):
            raise ValueError("published pins disagree with verified ledger")
        ledgers[name] = rows
    selected = {r["instance_id"]: r for r in candidates if r["corpus"] == corpus}
    ledger = ledgers[corpus]
    pins, statuses = [], {}
    for result in ledger:
        iid = result["instance_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", iid) or result["corpus"] != corpus:
            raise ValueError("invalid ledger identity")
        row = selected[iid]
        prefix = "evidence/" + iid + "/"
        canonical = row
        verdict = None
        if "canonical_expected" in result:
            logs = [read(prefix + arm + "/output/test.log") for arm in ("baseline", "gold")]
            canonical, mapping = canonicalize(row, *logs)
            if result["canonical_expected"] != {
                k: canonical[k] for k in ("FAIL_TO_PASS", "PASS_TO_PASS")
            }:
                raise ValueError("canonical identifiers differ from raw evidence")
            if result.get("source_identifier_audit", {}).get("mapping") != mapping:
                raise ValueError("canonical identifier mapping differs")
            phases = result["phases"]
            if len(phases) != 2:
                raise ValueError("canonical audit requires both phases")
            verdict = verify_gold(
                canonical["FAIL_TO_PASS"],
                canonical["PASS_TO_PASS"],
                *[
                    PhaseEvidence(log, phase["test"]["exit"])
                    for log, phase in zip(logs, phases, strict=True)
                ],
            )
            audit = result.get("contract_audit")
            expected_audit = {
                "valid": verdict.valid,
                "reason": verdict.reason,
                "baseline_statuses": verdict.baseline_statuses,
                "gold_statuses": verdict.gold_statuses,
            }
            if (
                audit != expected_audit
                or audit.get("valid") is not verdict.valid
                or verdict.valid is not result["valid"]
            ):
                raise ValueError("conservative contract audit differs from raw evidence")
        if verdict is not None and verdict.valid is True:
            if result.get("canonical_statuses") != [
                verdict.baseline_statuses,
                verdict.gold_statuses,
            ]:
                raise ValueError("verified canonical statuses differ from contract")
        audit_name = prefix + "source-identifier-audit.json"
        if audit_name in receipt.entries and obj(audit_name) != result.get(
            "source_identifier_audit"
        ):
            raise ValueError("per-task identifier audit differs from ledger")
        if result["valid"] is not True:
            if result["valid"] is not False and result["valid"] is not None:
                raise ValueError("invalid ledger outcome")
            statuses[iid] = "invalid" if result["valid"] is False else "unknown"
            continue
        row = selected[iid]
        if result["status"] != "verified" or result.get("attempted") is not True:
            raise ValueError("verified row lacks attempted execution")
        prefix = "evidence/" + iid + "/"
        if obj(prefix + "result.json") != result:
            raise ValueError("per-task result differs from ledger")
        phases = result["phases"]
        expected = tuple(canonical["FAIL_TO_PASS"] + canonical["PASS_TO_PASS"])
        if not row["FAIL_TO_PASS"] or len(set(expected)) != len(expected):
            raise ValueError("expected test IDs missing or duplicated")
        if len(phases) != 2:
            raise ValueError("both baseline and gold phases are required")
        for phase, arm in zip(phases, ("baseline", "gold"), strict=True):
            directory = prefix + arm + "/"
            inside = obj(directory + "output/inside.json")
            if (
                phase["phase"] != arm
                or type(phase["step"]["exit"]) is not int
                or type(phase["setup"]["exit"]) is not int
                or type(phase["test"]["exit"]) is not int
                or phase["step"]["exit"] != 0
                or phase["step"]["timeout"] is not False
                or phase["setup"]["exit"] != 0
                or phase.get("error")
                or phase["head"] != row["base_commit"]
            ):
                raise ValueError("failed phase cannot support admission")
            if any(phase.get(k) != v for k, v in inside.items()):
                raise ValueError("inside-image evidence differs from phase")
            if obj(directory + "input/task.json") != row:
                raise ValueError("executed task differs from source candidate")
            if (
                read(directory + "input/test.patch") != row["test_patch"]
                or read(directory + "input/gold.patch") != row["patch"]
            ):
                raise ValueError("executed patch differs from source candidate")
            from domains.swe_agents.environment.prun_contract import parse_pytest_summary

            states = parse_pytest_summary(read(directory + "output/test.log"), expected)
            if any(value is None for value in states.values()):
                raise ValueError("test evidence missing or conflicting")
            if verdict is None and states != phase["statuses"]:
                raise ValueError("reported test statuses differ from raw output")
            if arm == "baseline":
                good = (
                    phase["test"]["exit"] == 1
                    and all(
                        states[t] in (TestStatus.FAILED, TestStatus.ERROR)
                        for t in canonical["FAIL_TO_PASS"]
                    )
                    and all(states[t] == TestStatus.PASSED for t in canonical["PASS_TO_PASS"])
                )
            else:
                good = phase["test"]["exit"] == 0 and all(
                    s == TestStatus.PASSED for s in states.values()
                )
            if not good:
                raise ValueError("raw test output does not demonstrate required transitions")
        validate_backend(receipt, row, result)
        workdir = phases[0]["repo_path"]
        if workdir != phases[1]["repo_path"] or workdir not in (
            "/" + row["repo"].split("/")[-1],
            "/testbed",
        ):
            raise ValueError("inconsistent or unexpected task working directory")
        original = result["task_pin"]
        bound = {
            "key": iid,
            "repo": row["repo"],
            "url": "https://github.com/" + row["repo"],
            "commit": row["base_commit"],
            "issue": row["problem_statement"],
            "test_command": row["test_cmd"],
            "fail_to_pass": canonical["FAIL_TO_PASS"],
            "pass_to_pass": canonical["PASS_TO_PASS"],
            "gold_patch": row["patch"],
            "image": "sha256:" + result["image_sha256"],
        }
        if any(original.get(k) != v for k, v in bound.items()):
            raise ValueError("published pin differs from verified source fields")
        if digest(Path(row["image_path"])) != result["image_sha256"]:
            raise ValueError("verified image missing or changed")
        pin = TaskPin.model_validate(
            {
                **original,
                "image": row["image_path"],
                "image_sha256": result["image_sha256"],
                "verification_receipt": expected_manifest_sha256,
                "test_patch": row["test_patch"],
                "workdir": workdir,
                "python_env": "conda_testbed" if row["schema"] == "v1" else "image",
            }
        )
        pins.append(pin)
        statuses[iid] = "verified"
    return tuple(pins), statuses
