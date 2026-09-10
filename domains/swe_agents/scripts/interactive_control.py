"""Launch a registered four-cell diagnostic pilot against pinned local replicas."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from adversary.domain.perturbation import Perturbation
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.scripts.interactive_adversary import register, run_registered, save
from domains.swe_agents.scripts.interactive_episode import (
    episode_budget,
    load_host_pin,
    run_episode,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    budget_profile = config.get("budget_profile", "standard")
    max_steps, max_seconds = episode_budget(budget_profile)
    draft_path = Path(config["draft"])
    encoded = draft_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != config["draft_file_sha256"]:
        raise ValueError("frozen draft bytes differ")
    draft = ProbeDraft.model_validate_json(encoded)
    endpoints = config["endpoints"]
    if not endpoints or len(endpoints) != len(set(endpoints)):
        raise ValueError("unique deployed endpoints required")
    health = []
    for endpoint in endpoints:
        if not endpoint.startswith("http://127.0.0.1:") or not endpoint.endswith("/v1"):
            raise ValueError("only loopback deployment endpoints accepted")
        with urllib.request.urlopen(endpoint + "/models", timeout=5) as response:
            models = json.load(response)
        deployment = next(row for row in models["data"] if row["id"] == "devstral-base-rate")
        if not deployment["root"].endswith("55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128"):
            raise ValueError("endpoint checkpoint differs")
        health.append({"endpoint": endpoint, "deployment": deployment})
    tasks, bindings = [], {}
    for row in config["tasks"]:
        path = Path(row["path"])
        pin = TaskPin.model_validate_json((path / "original-pin.json").read_bytes())
        hp = load_host_pin(json.loads((path / "host-runtime-pin.json").read_text()))
        ref = (path / "prepared-ref.txt").read_text().strip()
        if pin.key in bindings:
            raise ValueError("duplicate task")
        bindings[pin.key] = (pin, hp, ref, path)
        tasks.append({"key": pin.key, "corpus": row["corpus"],
                      "host_repository_sha256": hp.repository_sha256,
                      "host_venv_sha256": hp.venv_sha256, "prepared_ref": ref})
    registration = register(
        draft, tasks, args.output, seed_base=config.get("seed_base", 2000),
        calibration_only=config.get("calibration_only", False),
    )
    save(args.output / "launch-config.json", config)
    save(args.output / "endpoints.json", health)
    for key, (_, _, _, path) in bindings.items():
        evidence = args.output / "pins" / key
        evidence.mkdir(parents=True)
        for name in ("original-pin.json", "host-runtime-pin.json", "prepared-ref.txt",
                     "baseline-untracked.json", "compatibility-exact.json", "versions.txt"):
            shutil.copyfile(path / name, evidence / name)
    assignment = {
        row["id"]: endpoints[index % len(endpoints)]
        for index, row in enumerate(registration["runs"])
    }
    save(args.output / "endpoint-assignment.json", assignment)

    def episode(run: dict[str, Any], perturbation: Perturbation, output: Path) -> dict[str, Any]:
        pin, hp, ref, _ = bindings[run["task"]["key"]]
        return run_episode(
            pin=pin, host_pin=hp, prepared_ref=ref, base_url=assignment[run["id"]],
            perturbation=perturbation, output=output, episode_id=run["id"],
            seed=run["seed"], host_nproc=config["host_nproc"],
            prompt_profile=config.get("prompt_profile", "legacy"),
            budget_profile=budget_profile, max_steps=max_steps, max_seconds=max_seconds,
        )

    summary = run_registered(args.output, episode, workers=config["workers"])
    headline = {key: value for key, value in summary.items() if key not in {"rows", "groups"}}
    print(json.dumps(headline), flush=True)


if __name__ == "__main__":
    main()
