"""Freeze schema-v2 source bindings before a proposal run; never fabricate measurements."""

import argparse
import json
from pathlib import Path

from adversary.core.model import PinField, TargetPin
from adversary.core.util import sha256_bytes, sha256_json, sha256_text, utc_now
from adversary.search.proposer import DRAFT_SCHEMA
from domains.swe_agents.environment.environment import TOOL_SPECS

ROOT = Path(__file__).resolve().parents[3]


def bindings(root: Path = ROOT) -> dict[str, str]:
    paths = sorted([*root.glob("adversary/**/*.py"), *root.glob("domains/swe_agents/**/*.py")])
    return {str(path.relative_to(root)): sha256_bytes(path.read_bytes()) for path in paths}


def mint(path: Path) -> dict:
    sources = bindings()
    scaffold = sha256_json(sources)
    target = TargetPin(
        model="gpt-6-astra",
        checkpoint=PinField(
            status="unpinned", reason="API does not expose immutable weight revision"
        ),
        quantisation=PinField(status="unpinned", reason="API does not expose internal precision"),
        serving_kernel=PinField(
            status="unpinned", reason="API does not expose serving stack revision"
        ),
        scaffold=PinField(status="pinned", value=scaffold),
        tool_set=PinField(status="pinned", value={"tools": TOOL_SPECS, "selection": "full"}),
        decoding_policy=PinField(
            status="pinned",
            value={
                "transport": "Responses",
                "reasoning_effort": "low",
                "temperature": "not sent",
                "top_p": "not sent",
                "seed": "not supported",
                "max_output_tokens_per_call": 4096,
                "max_steps": 50,
                "max_seconds": 1800,
                "total_token_cap": "unsupported; finite caps refuse",
            },
        ),
    )
    pin = {
        "pin_id": f"proposer/qwen3-8b/schema-v2/2026-09-10/{scaffold[:12]}",
        "recorded_at": utc_now().isoformat(),
        "scope": "configuration freeze; no admission measurement or live-serving attestation",
        "schema_version": 2,
        "schema_sha256": sha256_text(DRAFT_SCHEMA),
        "source_bindings": sources,
        "source_digest": scaffold,
        "proposer": {
            "model": "Qwen/Qwen3-8B",
            "revision": "b968826d9c46dd6066d109eabc6255188de91218",
            "revision_evidence": (
                "carried from historical pin; must verify live weights before sampling"
            ),
            "engine": "vllm==0.29.0",
            "dtype": "bfloat16",
            "quantisation": "none",
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "max_tokens": 4096,
            "enable_thinking": False,
            "seed_rule": "distinct preallocated draw indices",
        },
        "context": {
            "mined_seed": "required exact supplied record",
            "operator_register": "frozen digest",
            "task_pool": "externally anchored verified P-RUN receipt",
            "factor_space": None,
        },
        "channels": {
            "observation": "confined worker",
            "other": "refused: runtime gates unavailable",
        },
        "target_pin": target.model_dump(mode="json"),
        "target_pin_digest": target.fingerprint(),
        "measurement": None,
        "admission_refusal": (
            "Protected final oracle and complete production admission are not wired"
        ),
    }
    with path.open("x") as handle:
        json.dump(pin, handle, indent=2)
        handle.write("\n")
    return pin


def validate(path: Path) -> dict:
    pin = json.loads(path.read_text())
    if (
        pin["schema_sha256"] != sha256_text(DRAFT_SCHEMA)
        or pin["source_bindings"] != bindings()
        or pin["source_digest"] != sha256_json(pin["source_bindings"])
    ):
        raise ValueError("pin is stale; freeze a new pin before drawing evidence")
    if TargetPin.model_validate(pin["target_pin"]).fingerprint() != pin["target_pin_digest"]:
        raise ValueError("target pin digest differs")
    return pin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("mint", "validate"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    pin = mint(args.path) if args.action == "mint" else validate(args.path)
    print(
        json.dumps(
            {
                "pin": pin["pin_id"],
                "source_digest": pin["source_digest"],
                "measurement": pin["measurement"],
                "scope": pin["scope"],
            }
        )
    )


if __name__ == "__main__":
    main()
