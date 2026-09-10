"""Descriptive accounting for exactly one registered diagnostic arm."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from domains.swe_agents.scripts.interactive_adversary import summarize


def calibration_gate(group: dict[str, Any]) -> dict[str, Any]:
    """Fixed engineering headroom gate, never a confidence or population claim."""
    complete = group.get("complete") is True and group.get("executions") == 5
    eligible = complete and group.get("known") == 5 and group.get("passes", 0) >= 2
    return {"eligible": eligible, "engineering_only": True,
            "rule": "five attributable executions and at least two passes",
            "reason": "eligible" if eligible else "incomplete" if not complete else "low_headroom"}


def exclusive_reason(row: dict[str, Any]) -> str:
    """Priority partitions all registered executions; no censoring reason counted twice."""
    if row.get("missing"):
        return "missing_terminal"
    identity = row["cell_index"] == 0
    if row.get("control_identity_violation") or (identity and row.get("visible_changed")):
        return "control_identity_violation"
    if row.get("admission_status") == "rejected":
        return "admission_rejected"
    if row.get("status", "completed") != "completed" or type(
        row.get("diagnostic_passed")
    ) is not bool:
        return "infrastructure_or_verifier_unknown"
    if row.get("budget_exhausted", False):
        return "budget_censored"
    if (not identity and row.get("realized") is not True) or row.get(
        "clause_exposure_status", "verified" if identity else "unknown"
    ) != "verified":
        return "exposure_unknown"
    return "attributable_pass" if row["diagnostic_passed"] else "attributable_failure"


def quantile(values: list[float], probability: float) -> float | None:
    """Linear interpolation of observed finite wall times; no latency projection."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    left = math.floor(position)
    return ordered[left] + (ordered[math.ceil(position)] - ordered[left]) * (position - left)


def analyze(root: Path) -> dict[str, Any]:
    hashes: dict[str, str] = {}

    def read(path: Path) -> dict[str, Any]:
        if path.is_symlink():
            raise ValueError("receipt symlinks are not accepted")
        data = path.read_bytes()
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("receipt must be a JSON object")
        return value

    registration = read(root / "registration.json")
    integrity_path = root / "integrity-assessment.json"
    integrity = read(integrity_path) if integrity_path.exists() else {
        "status": "unknown", "reason": "no explicit arm integrity assessment",
    }
    if integrity.get("status") not in {"valid", "invalid", "unknown"}:
        raise ValueError("integrity status must be valid, invalid or unknown")
    config_path = root / "launch-config.json"
    config = read(config_path) if config_path.exists() else {}
    calibration = registration.get("never_pool_with_perturbation_arm") is True
    registered, rows, seen = [], [], set()
    for original in registration["runs"]:
        run = dict(original)
        name = run["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in seen:
            raise ValueError("invalid or duplicate registered identity")
        seen.add(name)
        directory = root / name
        if directory.is_symlink():
            raise ValueError("receipt directory symlinks are not accepted")
        if "task" not in run:
            metadata_path = directory / "metadata.json"
            meta = read(metadata_path) if metadata_path.exists() else {}
            run["task"] = {"key": meta.get("task_key", f"task-index-{run['task_index']}")}
        run.setdefault("cell_index", 0 if calibration else None)
        if type(run["cell_index"]) is not int or run["cell_index"] not in range(4):
            raise ValueError("invalid factorial cell")
        result = directory / "result.json"
        if calibration and not result.exists():
            result = directory / "episode.json"
        row = read(result) if result.exists() else {"missing": True}
        for field in ("id", "cell_index", "repetition", "seed"):
            if field in row and row[field] != run.get(field):
                raise ValueError("result differs from registration: " + field)
        if "task" in row and row["task"] != run["task"]:
            raise ValueError("result task differs from registration")
        if row.get("task_key", run["task"]["key"]) != run["task"]["key"]:
            raise ValueError("result task key differs from registration")
        registered.append(run)
        rows.append({**row, **run})
    summary_rows = [{**row, "status": "unknown"}
                    if exclusive_reason(row) == "admission_rejected" else row for row in rows]
    summary = summarize(summary_rows, registered_runs=registered)
    reasons = Counter(exclusive_reason(row) for row in rows)
    groups = []
    for group in summary["groups"]:
        n, known, passes = group["executions"], group["known"], group["passes"]
        failures, unknown = known - passes, n - known
        groups.append({**group, "known_failures": failures,
                       "failure_fraction_bounds": [failures / n, (failures + unknown) / n],
                       "bounds_kind": "identification bounds with all unknowns in denominator",
                       "pass_fraction_bounds": [passes / n, (passes + unknown) / n]})
    control = [{**g, "calibration_gate": calibration_gate(g)} for g in groups
               if g["cell_index"] == 0]
    for group in control:
        group["calibration_gate"]["outcome_threshold_met"] = group["calibration_gate"]["eligible"]
        if integrity["status"] != "valid":
            group["calibration_gate"].update(eligible=False, reason="integrity_not_valid")
    usage = {"input_tokens": 0, "output_tokens": 0}
    usage_known, walls, episode_rates = 0, [], []
    for row in rows:
        u = row.get("usage")
        valid = isinstance(u, dict) and all(type(u.get(k)) is int and u[k] >= 0 for k in usage)
        if valid:
            for key in usage:
                usage[key] += u[key]
        if valid and row.get("usage_unknown") is False and not row.get("missing"):
            usage_known += 1
        wall = row.get("wall_seconds")
        if type(wall) in (int, float) and math.isfinite(wall) and wall > 0:
            walls.append(float(wall))
            episode_rates.append({"id": row["id"], "wall_seconds": wall,
                                  "episodes_per_hour": 3600 / wall,
                                  "meaning": "reciprocal episode latency, not batch capacity"})
    stored = read(root / "summary.json") if (root / "summary.json").exists() else {}
    elapsed = stored.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
        elapsed = None
    terminal = len(rows) - reasons["missing_terminal"]
    completed = sum(row.get("status") == "completed" for row in rows)
    rates = {key: count * 3600 / elapsed if elapsed else None for key, count in {
        "terminal_per_hour": terminal, "completed_per_hour": completed,
        "diagnostic_measured_per_hour": summary["diagnostic_measured"],
        "attributable_per_hour": summary["attributable_known"],
    }.items()}
    return {"kind": "single_arm_descriptive_analysis", "never_pool_arms": True,
            "registration_kind": registration.get("kind"), "registered": len(rows),
            "integrity_assessment": integrity,
            "integrity_metadata": {k: v for k, v in config.items()
                                   if "integrity" in k or "history" in k},
            "causal_eligible": False,
            "integrity_gate_passed": integrity["status"] == "valid",
            "integrity_warning": ("Potential contamination: descriptive recorded outcomes only; "
                                  "not valid causal evidence.") if integrity["status"] != "valid"
                                 else "Integrity gate passed; design remains descriptive.",
            "terminal": terminal, "completed": completed, "exclusive_reasons": dict(reasons),
            "exclusive_reason_priority": ["missing_terminal", "control_identity_violation",
                                          "admission_rejected",
                                          "infrastructure_or_verifier_unknown",
                                          "budget_censored", "exposure_unknown",
                                          "attributable_pass", "attributable_failure"],
            "task_cells": groups, "control_headroom": control,
            "model_usage": {**usage, "episodes_with_complete_usage": usage_known,
                            "episodes_usage_unknown": len(rows) - usage_known,
                            "is_lower_bound": usage_known != len(rows)},
            "batch": {"elapsed_seconds": elapsed, **rates,
                      "basis": "recorded summary elapsed; no mtime or sum-of-latencies estimate"},
            "episode_walls": {"measured": len(walls), "p50_seconds": quantile(walls, .5),
                              "p90_seconds": quantile(walls, .9), "episodes": episode_rates},
            "protected": False, "confirmed": False, "inference": "descriptive only",
            "evidence_sha256": hashes}


def write_analysis(root: Path, output: Path) -> dict[str, Any]:
    report = analyze(root)
    output.mkdir(parents=True, exist_ok=False)
    (output / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Diagnostic arm analysis", "", report["integrity_warning"], "",
             f"Registered: {report['registered']}; terminal: {report['terminal']}; "
             f"completed: {report['completed']}.", "",
             "| Task | Cell | Attributable / registered | Passes | Failure bounds |",
             "|---|---:|---:|---:|---|"]
    for group in report["task_cells"]:
        low, high = group["failure_fraction_bounds"]
        lines.append(f"| {group['task']} | {group['cell_index']} | "
                     f"{group['known']} / {group['executions']} | {group['passes']} | "
                     f"[{low:.3f}, {high:.3f}] |")
    lines += ["", "Unknown outcomes remain in every bound's denominator. "
              "Calibration eligibility is an engineering gate, not statistical inference. "
              "No protected or confirmed claim. Arms are never pooled."]
    (output / "analysis.md").write_text("\n".join(lines) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_analysis(args.root, args.output)


if __name__ == "__main__":
    main()
