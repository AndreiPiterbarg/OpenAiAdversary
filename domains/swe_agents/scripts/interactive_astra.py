"""Four single-execution Astra cells; exploratory diagnostics, never five-run inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from adversary.core.model import Completion, CompletionRequest, Usage
from adversary.domain.perturbation import Perturbation
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.spec import TaskPin
from domains.swe_agents.scripts.factory_episode import RelayModel
from domains.swe_agents.scripts.interactive_adversary import run_registered, save
from domains.swe_agents.scripts.interactive_episode import load_host_pin, run_episode

SAMPLING = {"temperature": "provider_default", "seed": None, "reasoning_effort": "low"}


class AstraRelay(RelayModel):
    def __init__(self, episode: str, out: Path, *, call_limit: int = 20) -> None:
        if call_limit not in (20, 100):
            raise ValueError("unsupported explicit Astra call budget")
        self.call_limit = call_limit
        out.mkdir(parents=True, exist_ok=True)
        super().__init__(episode, out)
        self.completed_calls = 0
        self.usage = Usage()

    def complete(self, request: CompletionRequest) -> Completion:
        if self.calls >= self.call_limit or request.max_tokens > 1024:
            raise ValueError("Astra pilot call/output budget exhausted")
        request = request.model_copy(
            update={"temperature": 0, "seed": None, "reasoning_effort": "low"}
        )
        save(self.out / f"request-{self.calls + 1}.json", request.model_dump(mode="json"))
        result = super().complete(request)
        self.completed_calls += 1
        self.usage += result.usage
        return result


def registration(draft: ProbeDraft, task: dict) -> dict:
    if len(draft.clauses) != 2:
        raise ValueError("exactly two clauses required")
    encoded = draft.model_dump(mode="json")
    cells = [
        dict(zip(draft.clauses, levels, strict=True))
        for levels in (("off", "off"), ("on", "off"), ("off", "on"), ("on", "on"))
    ]
    return {
        "kind": "exploratory_astra_four_single_execution_cells",
        "draft": encoded,
        "draft_sha256": hashlib.sha256(json.dumps(encoded, sort_keys=True).encode()).hexdigest(),
        "tasks": [task],
        "runs": [
            {
                "id": f"astra-cell-{c}",
                "task": task,
                "cell": cell,
                "cell_index": c,
                "repetition": 0,
                "seed": 2000,
            }
            for c, cell in enumerate(cells)
        ],
        "protected": False,
        "confirmed": False,
        "trained": False,
        "api_sampling": SAMPLING,
        "seed_scope": "perturbation only; no API seed",
        "repetitions": 1,
        "order": "off/off, on/off, off/on, on/on; fixed before outcomes",
        "budget_per_episode": {"steps": 20, "seconds": 600, "output_per_call": 1024},
        "five_repetition_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    encoded = Path(config["draft"]).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != config["draft_file_sha256"]:
        raise ValueError("draft digest differs")
    draft = ProbeDraft.model_validate_json(encoded)
    path = Path(config["task_path"])
    pin = TaskPin.model_validate_json((path / "original-pin.json").read_bytes())
    if pin.key != "factoryboy__factory_boy-1067":
        raise ValueError("this pilot is restricted to the verified Factory task")
    hp = load_host_pin(json.loads((path / "host-runtime-pin.json").read_text()))
    ref = (path / "prepared-ref.txt").read_text().strip()
    compatibility = json.loads((path / "compatibility-exact.json").read_text())
    if not all(
        compatibility.get(k) is True
        for k in (
            "baseline_valid",
            "gold_valid",
            "single_commit_no_future_objects",
            "external_receipt_access_denied",
        )
    ):
        raise ValueError("history-free compatibility gates required")
    if (
        compatibility.get("host_pin_sha256")
        != hashlib.sha256((path / "host-runtime-pin.json").read_bytes()).hexdigest()
        or compatibility.get("prepared_ref") != ref
    ):
        raise ValueError("compatibility receipt does not bind runtime pin and prepared ref")
    args.output.mkdir(parents=True, exist_ok=False)
    task = {
        "key": pin.key,
        "corpus": "exploratory_discovery_only",
        "host_repository_sha256": hp.repository_sha256,
        "host_venv_sha256": hp.venv_sha256,
        "prepared_ref": ref,
    }
    save(args.output / "registration.json", registration(draft, task))
    save(args.output / "launch-config.json", config)
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
        shutil.copyfile(path / name, evidence / name)

    def episode(run: dict, perturbation: Perturbation, output: Path) -> dict:
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
            max_steps=20,
            max_seconds=600,
            model_override=AstraRelay(run["id"], output / "model"),
            sampling_policy=SAMPLING,
            prompt_profile=config.get("prompt_profile", "environment_guidance_v1"),
        )

    summary = run_registered(args.output, episode, workers=1)
    summary.update(
        kind="exploratory_astra_four_single_execution_cells", five_repetition_claim=False
    )
    save(args.output / "summary.json", summary)
    (args.output / "report.md").write_text(
        "# Exploratory Astra pilot\n\nFour single executions; no five-repetition, protected, "
        "or confirmed-mode claim. Consult summary.json and clause exposure receipts.\n"
    )
    print(
        json.dumps(
            {
                "event": "pilot_complete",
                "planned": 4,
                "diagnostic_measured": summary["diagnostic_measured"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
