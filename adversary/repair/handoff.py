"""Handing a fix set to training.

Training runs on the GPU box with kitchen's stack. This module writes what that run needs:
the examples as chat messages, the recipe (LoRA rank, replay ratio, seeds), and a manifest so
the payload can be verified after transfer. No training code lives here.
"""

import json
from pathlib import Path

import yaml
from pydantic import Field

from adversary.core.config import StrictModel
from adversary.core.manifest import build_manifest
from adversary.repair.fixset import FixSet


class RepairRecipe(StrictModel):
    """Training knobs recorded alongside the data; PALADIN-shaped defaults."""

    base_model: str = Field(description="Target checkpoint to adapt")
    lora_rank: int = Field(default=16, ge=1)
    replay_ratio: float = Field(
        default=1.0, ge=0.0, description="Generic agent data per fix example"
    )
    replay_source: str = Field(default="", description="Where replay data comes from")
    epochs: int = Field(default=2, ge=1)
    learning_rate: float = Field(default=1e-4, gt=0)
    seeds: int = Field(
        default=3, ge=1, description="Independent training seeds for the paired proof"
    )


class TrainingHandoff:
    """Writes a fix set and recipe into a directory under ``data/fixsets``."""

    def write(self, fixset: FixSet, recipe: RepairRecipe, directory: str | Path) -> Path:
        """Persist ``examples.jsonl``, ``recipe.yaml``, ``fixset.json`` and ``MANIFEST.json``."""
        if not fixset.examples or not fixset.recovery_model.shippable or any(
            not example.shippable for example in fixset.examples
        ):
            raise ValueError("training handoff requires nonempty verified licensed examples")
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        with open(target / "examples.jsonl", "w", encoding="utf-8") as handle:
            for example in fixset.examples:
                handle.write(
                    json.dumps(
                        {
                            "messages": [m.model_dump(mode="json") for m in example.messages],
                            "episode_id": example.episode_id,
                            "provenance": example.provenance.model_dump(mode="json"),
                        }
                    )
                    + "\n"
                )
        with open(target / "recipe.yaml", "w", encoding="utf-8") as handle:
            yaml.safe_dump(recipe.model_dump(mode="json"), handle, sort_keys=False)
        (target / "fixset.json").write_text(
            fixset.model_copy(update={"examples": ()}).model_dump_json(indent=2), encoding="utf-8"
        )
        build_manifest(target, note=f"fix set for mode {fixset.mode_id}").write(target)
        return target
