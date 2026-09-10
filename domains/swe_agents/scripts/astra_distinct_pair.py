"""One host-only Astra control/treatment execution for a distinct registered bug."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from adversary.core.factors import Cell
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.scripts.clause_exposure import clause_exposure
from domains.swe_agents.scripts.interactive_adversary import AuditedObservation, save
from domains.swe_agents.scripts.interactive_astra import SAMPLING, AstraRelay
from domains.swe_agents.scripts.interactive_episode import load_host_pin, run_episode


def pair_cell(draft: ProbeDraft, condition: str) -> Cell:
    if condition not in {"control", "treatment"} or not draft.clauses:
        raise ValueError("nonempty observation clauses and control or treatment required")
    if draft.perturbation is None or draft.channel is None or draft.channel.value != "observation":
        raise ValueError("observation program required")
    expected = Cell(levels={name: "on" if condition == "treatment" else "off"
                            for name in draft.clauses})
    if getattr(draft.pair, condition) != expected:
        raise ValueError("declared pair differs from fully switched condition")
    return expected


def validate_preparation(root: Path) -> tuple[TaskPin, Any, str]:
    pin = TaskPin.model_validate_json((root / "original-pin.json").read_bytes())
    encoded = (root / "host-runtime-pin.json").read_bytes()
    hp = load_host_pin(json.loads(encoded))
    ref = (root / "prepared-ref.txt").read_text().strip()
    gate = json.loads((root / "compatibility-exact.json").read_text())
    if not all(gate.get(key) is True for key in (
        "baseline_valid", "gold_valid", "single_commit_no_future_objects",
        "external_receipt_access_denied",
    )):
        raise ValueError("history-free guarded baseline/gold preparation required")
    if (gate.get("host_pin_sha256") != hashlib.sha256(encoded).hexdigest()
            or gate.get("prepared_ref") != ref or not re.fullmatch(r"[0-9a-f]{40}", ref)):
        raise ValueError("preparation receipt binding differs")
    if hp.task_key != pin.key or hp.commit != pin.commit:
        raise ValueError("host pin task identity differs")
    return pin, hp, ref


def execute(pin_root: Path, draft_path: Path, condition: str, output: Path,
            episode_id: str, host_nproc: int = 1536) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", episode_id):
        raise ValueError("safe episode identity required")
    output.mkdir(parents=True, exist_ok=False)
    registration: dict[str, Any] = {
        "id": episode_id, "condition": condition, "repetition": 0,
        "kind": "distinct_bug_single_control_or_treatment", "planned": 1,
        "protected": False, "confirmed": False, "five_repetition_claim": False,
        "sampling_policy": SAMPLING,
        "budget": {"max_steps": 100, "max_seconds": 600, "max_tokens": 1024},
        "observation_limit": 16000, "host_nproc": host_nproc,
    }
    save(output / "registration.json", registration)
    observation = None
    row: dict[str, Any] = {}
    try:
        draft_bytes = draft_path.read_bytes()
        draft = ProbeDraft.model_validate_json(draft_bytes)
        cell = pair_cell(draft, condition)
        pin, hp, ref = validate_preparation(pin_root)
        registration.update(task_key=pin.key, cell=dict(cell.levels), prepared_ref=ref,
                            draft_sha256=hashlib.sha256(draft_bytes).hexdigest(),
                            original_pin_sha256=hashlib.sha256(
                                (pin_root / "original-pin.json").read_bytes()).hexdigest())
        save(output / "registration.json", registration)
        (output / "draft.json").write_bytes(draft_bytes)
        evidence = output / "pins"
        evidence.mkdir()
        for name in ("original-pin.json", "host-runtime-pin.json", "prepared-ref.txt",
                     "baseline-untracked.json", "compatibility-exact.json"):
            shutil.copyfile(pin_root / name, evidence / name)
        observation = AuditedObservation(draft, cell, 0, output)
        row = run_episode(
            pin=pin, host_pin=hp, prepared_ref=ref, base_url="local_credential_bridge",
            perturbation=observation, output=output, episode_id=episode_id, seed=0,
            host_nproc=host_nproc, max_steps=100, max_seconds=600,
            model_override=AstraRelay(episode_id, output / "model", call_limit=100),
            prompt_profile="environment_guidance_v1", sampling_policy=SAMPLING,
            observation_limit=16000,
        )
        exposure = clause_exposure(draft, cell, 0, observation.prepare_spec, observation.records)
        save(output / "clause-exposure.json", exposure)
        row.update(realized=exposure["realized"], clause_exposure_status=exposure["status"],
                   clause_visible_contribution=exposure["clause_visible_contribution"],
                   visible_changed=any(r["visible_trigger"] for r in observation.records))
        row["control_identity_violation"] = condition == "control" and row["visible_changed"]
        if row["control_identity_violation"]:
            row.update(status="unknown", diagnostic_passed=None)
    except Exception as exc:
        row.update(status="unknown", diagnostic_passed=None,
                   error_type=type(exc).__name__, reason=str(exc))
    finally:
        if observation is not None:
            try:
                observation.close()
            except Exception as exc:
                row.update(status="unknown", diagnostic_passed=None,
                           cleanup_error_type=type(exc).__name__)
    row.update(registration)
    save(output / "result.json", row)
    save(output / "summary.json", row)
    print(json.dumps({"event": "episode_complete", "episode_id": episode_id,
                      "summary": row}), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin-root", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--condition", choices=("control", "treatment"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--host-nproc", type=int, default=1536)
    args = parser.parse_args()
    execute(args.pin_root, args.draft, args.condition, args.output,
            args.episode_id, args.host_nproc)


if __name__ == "__main__":
    main()
