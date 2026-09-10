"""Fixed sixty-episode Astra registration, executed in twelve independently bound shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from adversary.domain.perturbation import Perturbation
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.scripts.interactive_adversary import (
    register,
    run_registered,
    save,
    summarize,
)
from domains.swe_agents.scripts.interactive_astra import SAMPLING, AstraRelay
from domains.swe_agents.scripts.interactive_episode import load_host_pin, run_episode


def build_manifest(config: dict) -> dict:
    encoded = Path(config["draft"]).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != config["draft_file_sha256"]:
        raise ValueError("frozen draft digest differs")
    draft = ProbeDraft.model_validate_json(encoded)
    if len(config["tasks"]) not in (1, 3):
        raise ValueError("batch requires one discovery task or three transfer tasks")
    observation_limit = config.get("observation_limit", 4000)
    request_byte_bound = config.get("request_byte_bound", 262144)
    if type(observation_limit) is not int or observation_limit not in (4000, 16000):
        raise ValueError("unsupported observation limit")
    if type(request_byte_bound) is not int or request_byte_bound not in (262144, 1000000):
        raise ValueError("unsupported request byte bound")
    tasks = []
    for row in config["tasks"]:
        root = Path(row["path"])
        pin = TaskPin.model_validate_json((root / "original-pin.json").read_bytes())
        raw = (root / "host-runtime-pin.json").read_bytes()
        hp = load_host_pin(json.loads(raw))
        ref = (root / "prepared-ref.txt").read_text().strip()
        check = json.loads((root / "compatibility-exact.json").read_text())
        if not all(
            check.get(k) is True
            for k in (
                "baseline_valid",
                "gold_valid",
                "single_commit_no_future_objects",
                "external_receipt_access_denied",
            )
        ):
            raise ValueError("history-free compatibility gates required")
        if (
            check.get("host_pin_sha256") != hashlib.sha256(raw).hexdigest()
            or check.get("prepared_ref") != ref
        ):
            raise ValueError("compatibility pin binding differs")
        if hp.task_key != pin.key or hp.commit != pin.commit:
            raise ValueError("host task binding differs")
        tasks.append(
            {
                "key": pin.key,
                "corpus": row["corpus"],
                "host_repository_sha256": hp.repository_sha256,
                "host_venv_sha256": hp.venv_sha256,
                "prepared_ref": ref,
                "original_pin_sha256": hashlib.sha256(
                    (root / "original-pin.json").read_bytes()
                ).hexdigest(),
            }
        )
    with tempfile.TemporaryDirectory(prefix="astra-registration-") as temporary:
        manifest = register(
            draft, tasks, Path(temporary) / "registration", seed_base=config.get("seed_base", 5000)
        )
    manifest.update(
        kind="astra_sixty_episode_diagnostic_batch" if len(tasks) == 3
        else "astra_twenty_episode_discovery_batch",
        api_sampling=SAMPLING,
        budget_per_episode={"steps": 100, "seconds": 600, "output_per_call": 1024},
        api_seed=None,
        seed_scope="perturbation only",
        target_model="gpt-6-astra",
        request_byte_bound=request_byte_bound,
        observation_limit=observation_limit,
        total_token_bound=None,
        cross_model_comparability_claim=False,
    )
    return manifest


def shard_registration(manifest: dict, task_index: int, cell_index: int) -> dict:
    if (
        type(task_index) is not int
        or task_index not in range(len(manifest["tasks"]))
        or type(cell_index) is not int
        or cell_index not in range(4)
    ):
        raise ValueError("invalid shard indices")
    task = manifest["tasks"][task_index]
    rows = [
        row
        for row in manifest["runs"]
        if row["task"]["key"] == task["key"] and row["cell_index"] == cell_index
    ]
    if len(rows) != 5 or {row["repetition"] for row in rows} != set(range(5)):
        raise ValueError("shard must bind five distinct registered repetitions")
    return {
        **manifest,
        "runs": rows,
        "shard": {"task_index": task_index, "cell_index": cell_index},
        "canonical_manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
    }


def aggregate(manifest: dict, shard_paths: list[Path]) -> dict:
    rows = []
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    for path in shard_paths:
        registration = json.loads((path / "registration.json").read_text())
        if registration.get("canonical_manifest_sha256") != digest:
            raise ValueError("shard canonical manifest differs")
        for run in registration["runs"]:
            result = path / run["id"] / "result.json"
            if result.exists():
                rows.append(json.loads(result.read_text()))
    summary = summarize(rows, registered_runs=manifest["runs"])
    return {
        **summary,
        "kind": manifest.get("kind", "astra_sixty_episode_diagnostic_batch"),
        "rows": rows,
        "protected": False,
        "confirmed": False,
        "canonical_manifest_sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-index", type=int, required=True)
    parser.add_argument("--cell-index", type=int, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    manifest = build_manifest(config)
    registration = shard_registration(manifest, args.task_index, args.cell_index)
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "canonical-registration.json", manifest)
    save(args.output / "registration.json", registration)
    save(args.output / "launch-config.json", config)
    root = Path(config["tasks"][args.task_index]["path"])
    pin = TaskPin.model_validate_json((root / "original-pin.json").read_bytes())
    hp = load_host_pin(json.loads((root / "host-runtime-pin.json").read_text()))
    ref = (root / "prepared-ref.txt").read_text().strip()
    evidence = args.output / "pins"
    evidence.mkdir()
    for name in (
        "original-pin.json",
        "host-runtime-pin.json",
        "prepared-ref.txt",
        "baseline-untracked.json",
        "compatibility-exact.json",
        "versions.txt",
    ):
        shutil.copyfile(root / name, evidence / name)

    def episode(run: dict, perturbation: Perturbation, output: Path) -> dict[str, Any]:
        return run_episode(
            pin=pin,
            host_pin=hp,
            prepared_ref=ref,
            base_url="local_credential_bridge",
            perturbation=perturbation,
            output=output,
            episode_id=run["id"],
            seed=run["seed"],
            host_nproc=config["host_nproc"],
            max_steps=100,
            max_seconds=600,
            model_override=AstraRelay(run["id"], output / "model", call_limit=100),
            sampling_policy=SAMPLING,
            prompt_profile=config.get("prompt_profile", "environment_guidance_v1"),
            observation_limit=config.get("observation_limit", 4000),
        )

    summary = run_registered(args.output, episode, workers=1)
    print(
        json.dumps(
            {
                "event": "shard_complete",
                "planned": 5,
                "diagnostic_measured": summary["diagnostic_measured"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
