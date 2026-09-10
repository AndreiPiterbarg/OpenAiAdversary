"""Read-only postprocessing of finished throughput arms; no runtime or network imports.

Copy this standalone script outside a deployed source snapshot if running on the
cluster. --native-receipt-mtimes is only valid on original files or copies made
with timestamp preservation; its timing is a projection interval, not HTTP time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def read(path: Path) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            value[key] = item
        return value

    def invalid(value: str) -> None:
        raise ValueError(f"non-finite JSON number in {path}: {value}")

    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def distribution(values: list[float]) -> dict[str, Any]:
    values = sorted(values)
    return {
        "n": len(values),
        "sum": sum(values),
        "mean": sum(values) / len(values) if values else None,
        "p50": values[math.ceil(0.5 * len(values)) - 1] if values else None,
        "p95": values[math.ceil(0.95 * len(values)) - 1] if values else None,
    }


def call_metrics(root: Path, *, native_mtimes: bool) -> dict[str, Any]:
    original = sorted(root.glob("call-*-original-request.json"))
    contexts = sorted(root.glob("call-*-context.json"))
    completed = sorted(root.glob("call-*-completion.json"))
    model_seconds, projection_seconds = [], []
    input_tokens = output_tokens = trials = 0
    missing_usage = 0
    for path in completed:
        value = read(path)
        usage = value.get("raw", {}).get("usage", {})
        if all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens")
        ):
            input_tokens += usage["prompt_tokens"]
            output_tokens += usage["completion_tokens"]
        else:
            missing_usage += 1
        duration = value.get("usage", {}).get("wall_seconds")
        if number(duration):
            model_seconds.append(duration)
    for path in contexts:
        value = read(path)
        trials += len(value.get("tokenization_trials", []))
        before = path.with_name(path.name.replace("-context.json", "-original-request.json"))
        if native_mtimes and before.is_file():
            seconds = (path.stat().st_mtime_ns - before.stat().st_mtime_ns) / 1e9
            if seconds < 0:
                raise ValueError("receipt timestamps are not ordered; do not claim native timing")
            projection_seconds.append(seconds)
    uncertain = [p for p in root.glob("*-failure.json") if read(p).get("usage_unknown") is True]
    failure = root / "failure.json"
    failure_value = read(failure) if failure.exists() else {}
    if failure_value.get("usage_unknown") is True:
        uncertain.append(failure)
    missing_terminal = 0
    for path in original:
        stem = path.name.removesuffix("-original-request.json")
        if (root / (stem + "-completion.json")).exists():
            continue
        stop = root / (stem + "-budget-stop.json")
        if stop.exists() and read(stop).get("model_attempted") is False:
            continue
        if (
            path == original[-1]
            and failure_value.get("stage") in {"request_validation", "context_projection"}
            and failure_value.get("usage_unknown") is False
        ):
            continue
        missing_terminal += 1
    return {
        "model_requests": len(original),
        "model_completions": len(completed),
        "measured_input_tokens": input_tokens,
        "measured_output_tokens": output_tokens,
        "completions_missing_usage": missing_usage,
        "usage_unknown": bool(uncertain) or missing_usage > 0 or missing_terminal > 0,
        "requests_without_accounted_completion": missing_terminal,
        "model_request_wall_seconds": distribution(model_seconds),
        "recorded_tokenizer_trials": trials,
        "tokenizer_http_seconds": None,
        "context_projection_receipt_seconds": distribution(projection_seconds)
        if native_mtimes
        else None,
        "timing_scope": (
            "model HTTP wall time from completion usage; "
            "optional projection interval includes bookkeeping"
        ),
        "tokenizer_trial_count_scope": (
            "successful saved contexts only; failed projection trials may be unrecorded"
        ),
    }


def load_arm(label: str, root: Path, *, native_mtimes: bool = False) -> dict[str, Any]:
    registration = read(root / "registration.json")
    final = read(root / "summary.json")
    config = registration["config"]
    tasks = config["tasks"]
    keys = [task["key"] for task in tasks]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate registered task keys")
    elapsed = final.get("elapsed_seconds_including_stagger_and_cleanup")
    if not number(elapsed) or elapsed == 0:
        raise ValueError("finished arm lacks a positive measured wall duration")
    expected = set(keys)
    progress: dict[str, Any] = {}
    for path in (root / "progress").glob("*.json"):
        value = read(path)
        key = value.get("key")
        if key not in expected or key in progress:
            raise ValueError("progress keys differ from registered denominator")
        if value.get("status") == "running":
            raise ValueError("arm still contains running episodes")
        progress[key] = value
    counts = {
        key: 0
        for key in (
            "planned",
            "attempted",
            "terminal_attempts",
            "controller_completed",
            "tested",
            "passed",
            "failed",
            "rejected",
            "unknown",
            "not_attempted",
            "missing_terminal_record",
            "budget_exhausted",
        )
    }
    counts["planned"] = len(tasks)
    episodes = []
    ownership = registration.get("owned_step_names", [])
    if ownership and len(ownership) != len(tasks):
        raise ValueError("ownership list differs from task denominator")
    timings: dict[str, list[float]] = {
        k: []
        for k in (
            "elapsed_seconds",
            "first_model_request_seconds",
            "setup_seconds",
            "interaction_seconds",
            "verification_seconds",
            "gold_control_seconds",
        )
    }
    for index, task in enumerate(tasks):
        record = progress.get(task["key"])
        episode = (record or {}).get("episode", {})
        if record is None:
            category = "unknown"
            counts["missing_terminal_record"] += 1
        elif record.get("status") == "not_attempted":
            category = "not_attempted"
        else:
            counts["attempted"] += 1
            counts["terminal_attempts"] += 1
            completed = episode.get("status") == "completed"
            counts["controller_completed"] += int(completed)
            if episode.get("admission_status") == "rejected":
                category = "rejected"
            elif completed and type(episode.get("diagnostic_passed")) is bool:
                counts["tested"] += 1
                category = "passed" if episode["diagnostic_passed"] else "failed"
            else:
                category = "unknown"
        counts[category] += 1
        counts["budget_exhausted"] += int(episode.get("budget_exhausted") is True)
        item = {
            "key": task["key"],
            "corpus": task.get("corpus"),
            "category": category,
            "stop_reason": episode.get("stop_reason"),
            "budget_exhausted": episode.get("budget_exhausted"),
            "failure_stage": episode.get("failure_stage"),
            "reason": episode.get("reason", (record or {}).get("reason")),
            "controller_model_calls": episode.get("model_calls"),
            "timings": {},
        }
        for field in timings:
            value = (
                (record or {}).get(field)
                if field in {"elapsed_seconds", "first_model_request_seconds"}
                else episode.get(field)
            )
            if number(value):
                timings[field].append(value)
                item["timings"][field] = value
        if ownership:
            name = ownership[index]
            if Path(name).name != name or name in {".", ".."}:
                raise ValueError("unsafe bridge ownership name")
            item["calls"] = call_metrics(root / "bridge" / name, native_mtimes=native_mtimes)
        episodes.append(item)
    counts["unresolved_total"] = counts["rejected"] + counts["unknown"]
    counts["without_diagnostic_verdict"] = counts["unresolved_total"] + counts["not_attempted"]
    call_fields = (
        "model_requests",
        "model_completions",
        "measured_input_tokens",
        "measured_output_tokens",
        "completions_missing_usage",
        "recorded_tokenizer_trials",
    )
    calls = {key: sum(e.get("calls", {}).get(key, 0) for e in episodes) for key in call_fields}
    calls["episodes_with_unknown_usage"] = sum(
        e.get("calls", {}).get("usage_unknown", False) for e in episodes
    )
    calls["model_request_wall_seconds"] = sum(
        e.get("calls", {}).get("model_request_wall_seconds", {}).get("sum", 0) for e in episodes
    )
    calls["tokenizer_http_seconds"] = None
    calls["context_projection_receipt_seconds"] = (
        sum(
            (e.get("calls", {}).get("context_projection_receipt_seconds") or {}).get("sum", 0)
            for e in episodes
        )
        if native_mtimes
        else None
    )
    pin_rows = registration.get("task_pins", [])
    pin_bindings = {p["key"]: p["sha256"] for p in pin_rows}
    if len(pin_rows) != len(tasks):
        raise ValueError("pin binding count differs from registered tasks")
    if set(pin_bindings) != expected:
        raise ValueError("registration lacks complete frozen task-pin hashes")
    return {
        "label": label,
        "root": str(root),
        "k": config["k"],
        "counts": counts,
        "elapsed_seconds": elapsed,
        "terminal_attempts_per_hour": counts["terminal_attempts"] * 3600 / elapsed,
        "completed_episodes_per_hour": counts["controller_completed"] * 3600 / elapsed,
        "diagnostic_verdicts_per_hour": counts["tested"] * 3600 / elapsed,
        "timings": {k: distribution(v) for k, v in timings.items()},
        "calls": calls,
        "episodes": episodes,
        "pin_bindings": pin_bindings,
        "source_manifest_sha256": registration.get("source_manifest_sha256"),
        "budget": config["budget"],
        "server_settings": config["server_settings"],
        "cleanup_verified": final.get("cleanup_verified") is True,
        "interrupted": final.get("interrupted"),
        "registration_sha256": hashlib.sha256(
            (root / "registration.json").read_bytes()
        ).hexdigest(),
        "summary_sha256": hashlib.sha256((root / "summary.json").read_bytes()).hexdigest(),
        "protected_status": "unknown",
        "clean_solve_eligible": False,
    }


def compare(arms: list[dict[str, Any]]) -> dict[str, Any]:
    if len(arms) != 2:
        return {"available": False, "reason": "exactly two arms required for paired description"}
    first, second = arms
    keys = set(first["pin_bindings"]) & set(second["pin_bindings"])
    matched = [k for k in sorted(keys) if first["pin_bindings"][k] == second["pin_bindings"][k]]
    pairs = []
    lookup = [{e["key"]: e for e in arm["episodes"]} for arm in arms]
    for key in matched:
        pairs.append(
            {
                "key": key,
                first["label"]: lookup[0][key]["category"],
                second["label"]: lookup[1][key]["category"],
            }
        )
    same = first["pin_bindings"] == second["pin_bindings"]
    return {
        "available": True,
        "same_registered_task_pins": same,
        "matched_task_count": len(matched),
        "same_budget": first["budget"] == second["budget"],
        "same_source_manifest": first["source_manifest_sha256"] == second["source_manifest_sha256"],
        "same_declared_server_settings": first["server_settings"] == second["server_settings"],
        "matched_outcomes": pairs,
        "caveat": (
            "Sequential arms are not randomized: page-cache warmth, server caches and "
            "cluster load can affect the later arm. Rates describe observed wall time, "
            "not projected capacity or protected clean-solve rates."
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    columns = [
        "Arm",
        "Planned",
        "Terminal",
        "Tested",
        "Passed",
        "Failed",
        "Rejected",
        "Unknown",
        "Not attempted",
        "Completed/h",
        "Verdicts/h",
    ]
    lines = [
        "Observed diagnostic throughput",
        "",
        "| " + " | ".join(columns) + " |",
        "|---|" + "---:|" * (len(columns) - 1),
    ]
    for arm in report["arms"]:
        c = arm["counts"]
        label = arm["label"].replace("|", "\\|").replace("\n", " ")
        values = [
            label,
            *(
                str(c[k])
                for k in (
                    "planned",
                    "terminal_attempts",
                    "tested",
                    "passed",
                    "failed",
                    "rejected",
                    "unknown",
                    "not_attempted",
                )
            ),
            f"{arm['completed_episodes_per_hour']:.1f}",
            f"{arm['diagnostic_verdicts_per_hour']:.1f}",
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines += [
        "",
        "Rejected, unknown and unattempted tasks remain in the registered denominator. "
        "Completed episodes include recorded rejections; verdict throughput counts only "
        "actual diagnostic pass/fail results. Budget exhaustion is recorded separately.",
        "",
    ]
    for arm in report["arms"]:
        c = arm["calls"]
        mean = arm["timings"]["elapsed_seconds"]["mean"]
        mean_text = f"{mean:.1f}s" if mean is not None else "unavailable"
        seconds = c["context_projection_receipt_seconds"]
        timing = "unavailable" if seconds is None else f"{seconds:.1f}s (includes bookkeeping)"
        lines.append(
            f"{arm['label']}: {arm['elapsed_seconds']:.1f}s observed arm wall time; "
            f"attempt elapsed mean {mean_text}. {c['model_requests']} recorded requests, "
            f"{c['model_completions']} completions, {c['measured_input_tokens']} measured input "
            f"tokens and {c['measured_output_tokens']} output tokens. "
            f"{c['recorded_tokenizer_trials']} recorded tokenizer trials; projection time "
            f"{timing}. HTTP-only tokenizer duration was not recorded."
        )
        if arm.get("interrupted"):
            lines.append(
                "This arm was interrupted: elapsed attempt times include canceled work; "
                "these rates do not estimate completed steady-state capacity."
            )
        if not arm["cleanup_verified"]:
            lines.append("Owned-resource cleanup was not fully verified for this arm.")
    lines += [
        "",
        report["comparison"].get(
            "caveat", "Protected status remains unknown; these are diagnostic measurements."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-receipt-mtimes", action="store_true")
    args = parser.parse_args()
    arms = []
    labels = set()
    for item in args.arm:
        label, separator, path = item.partition("=")
        if not separator or not label or label in labels:
            parser.error("each arm needs a unique LABEL=PATH")
        labels.add(label)
        arms.append(load_arm(label, Path(path), native_mtimes=args.native_receipt_mtimes))
    report = {
        "kind": "throughput_observed_report_v1",
        "arms": arms,
        "comparison": compare(arms),
        "native_receipt_mtimes_attested": args.native_receipt_mtimes,
        "report_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (args.output / "results.md").write_text(markdown(report))


if __name__ == "__main__":
    main()
