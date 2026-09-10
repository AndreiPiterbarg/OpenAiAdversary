"""Read-only public aggregates from one registered arm; never combine calibration and treatment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from domains.swe_agents.scripts.interactive_adversary import summarize


def export_results(root: Path, destination: Path) -> dict[str, Any]:
    hashes: dict[str, str] = {}

    def read(path: Path) -> dict[str, Any]:
        encoded = path.read_bytes()
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(encoded).hexdigest()
        return json.loads(encoded)

    registration = read(root / "registration.json")
    calibration = registration.get("never_pool_with_perturbation_arm") is True
    directories = {}
    shards = sorted((root / "shards").glob("*/registration.json"))
    if shards:
        canonical = hashlib.sha256(json.dumps(registration, sort_keys=True).encode()).hexdigest()
        assignments = {run["id"]: run for run in registration["runs"]}
        if len(assignments) != len(registration["runs"]):
            raise ValueError("duplicate canonical assignment")
        for path in shards:
            shard = read(path)
            if shard.get("canonical_manifest_sha256") != canonical:
                raise ValueError("shard canonical manifest differs")
            for run in shard["runs"]:
                if run != assignments.get(run["id"]):
                    raise ValueError("shard assignment differs from canonical registration")
                if run["id"] in directories:
                    raise ValueError("duplicate shard assignment")
                directories[run["id"]] = path.parent / run["id"]
    registered, rows, pending = [], [], []
    for original in registration["runs"]:
        run = dict(original)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run["id"]):
            raise ValueError("invalid registered run path")
        directory = directories.get(run["id"], root / run["id"])
        if "task" not in run:
            metadata_path = directory / "metadata.json"
            metadata = read(metadata_path) if metadata_path.exists() else {}
            run["task"] = {"key": metadata.get("task_key", f"task-index-{run['task_index']}")}
        run.setdefault("cell_index", 0 if calibration else None)
        if run["cell_index"] not in range(4):
            raise ValueError("registered factorial cell is missing")
        registered.append(run)
        result = directory / "result.json"
        if not result.exists() and calibration:
            result = directory / "episode.json"
        if not result.exists():
            pending.append(run["id"])
            continue
        row = read(result)
        for key in ("id", "cell_index", "repetition", "seed", "cell", "task"):
            if key in row and row[key] != run.get(key):
                raise ValueError("result differs from registered assignment: " + key)
        if row.get("task_key", run["task"]["key"]) != run["task"]["key"]:
            raise ValueError("result task differs from registration")
        rows.append({**row, **run})
    summary = summarize(rows, registered_runs=registered)
    # A pure control calibration has no factorial contrast by construction.
    if calibration:
        summary["contrasts"] = []
    failures = Counter(
        (row.get("stage", row.get("failure_stage", "unspecified")),
         row.get("error_type", "unknown"))
        for row in rows if row.get("status") == "unknown"
    )
    outcome_counts = Counter()
    for row in rows:
        if row.get("admission_status") == "rejected":
            outcome_counts["admission_rejected"] += 1
        elif type(row.get("diagnostic_passed")) is bool:
            outcome_counts["diagnostic_measured"] += 1
        else:
            outcome_counts["infrastructure_or_verifier_unknown"] += 1
    outcome_counts["pending_or_missing"] = len(pending)
    report = {
        "kind": "registered_interactive_public_results_v1",
        "arm_kind": "calibration_only" if calibration else "generated_four_cell_pilot",
        "never_pool_with_other_arms": True,
        "registration_kind": registration.get("kind"),
        "summary": summary,
        "terminal_receipts": len(rows),
        "rows": rows,
        "terminal_outcome_counts": dict(outcome_counts),
        "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pending_or_missing": len(pending),
        "pending_run_ids": pending,
        "unknown_by_stage": [dict(stage=stage, error_type=error, executions=count)
                             for (stage, error), count in sorted(failures.items())],
        "evidence_sha256": hashes,
        "limitations": [
            "Host runtime differs from the original container runtime.",
            "Same-process pytest outputs are diagnostic, not protected semantic evidence.",
            "Unrealized active conditions and censored runs remain attributable unknowns.",
            "Five repeated executions per task do not establish population generalization.",
            "No trained, protected, confirmed, or confidence-interval claim.",
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(destination)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = export_results(args.root, args.destination)
    print(json.dumps({"planned": report["summary"]["planned"],
                      "terminal_receipts": report["terminal_receipts"],
                      "attributable_known": report["summary"]["attributable_known"],
                      "unknown": report["summary"]["unknown"]}))


if __name__ == "__main__":
    main()
