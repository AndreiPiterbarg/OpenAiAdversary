"""Fixed conditional structural draw; not full admission or task execution."""

import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path

from adversary.core.factors import Cell
from adversary.core.model import LicenseClass
from adversary.core.util import sha256_json, utc_now
from adversary.execution.backends.openai_compatible import ServedModel
from adversary.probe.executor import ConfinedPrograms
from adversary.probe.program import ProgramKind, ProgramSource
from adversary.search.context import MinedSeed, SearchContext
from adversary.search.critic import StaticCritic
from adversary.search.proposer import LLMProposer, ProposalError
from adversary.stats.recall import clopper_pearson
from domains.swe_agents.environment.spec import SweOracle, SweTaskSpec, TaskPin
from domains.swe_agents.scripts.pin_contract import validate


class RemotePrograms(ConfinedPrograms):
    def __init__(self, remote_root: str):
        super().__init__()
        self.remote_root = remote_root
        self.infrastructure_errors = []

    def _call(self, program, **request):
        command = (
            "cd "
            + shlex.quote(self.remote_root)
            + " && /home/guests/andrei/va/.venv-vllm/bin/python -m tests.program_rpc"
        )
        try:
            process = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10", "worker-4", command],
                input=json.dumps({"program": program.model_dump(mode="json"), **request}),
                text=True,
                capture_output=True,
                timeout=40,
                check=True,
            )
            reply = json.loads(process.stdout)
        except Exception as exc:
            self.infrastructure_errors.append(repr(exc))
            raise
        if "program_error" in reply:
            raise ValueError(reply["program_error"])
        return reply["result"]


class RecordingModel(ServedModel):
    def complete(self, request):
        self.request_record = request.model_dump(mode="json")
        self.completion_record = None
        completion = super().complete(request)
        self.completion_record = completion.model_dump(mode="json")
        return completion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pin", type=Path, default=Path("tests/evidence/proposer_pin_v2.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pin_path = args.pin.resolve()
    pin = validate(pin_path)
    input_path = root / "tests/evidence/structural_v2_inputs.json"
    data = json.loads(input_path.read_text())
    seed = MinedSeed.model_validate(data["seed"])
    raw = data["candidate"]
    task = TaskPin(
        key=raw["instance_id"],
        repo=seed.repo,
        url="https://github.com/" + seed.repo,
        commit=raw["base_commit"],
        issue=raw["problem_statement"],
        test_command=raw["install_config"]["test_cmd"],
        fail_to_pass=tuple(raw["FAIL_TO_PASS"]),
        pass_to_pass=tuple(raw["PASS_TO_PASS"]),
        properties={},
        image=raw["image_path"],
        gold_patch=raw["patch"],
    )
    spec = SweTaskSpec(pin=task, canary="structural-only")
    oracle = SweOracle(
        test_command=task.test_command,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
        gold_patch=task.gold_patch,
        canary=spec.canary,
    )
    config = {
        "spec": spec.model_dump(mode="json"),
        "oracle": oracle.model_dump(mode="json"),
        "resource": task.repo,
        "source_license": raw.get("license"),
    }
    context = SearchContext(mined_seed=seed)
    executor = RemotePrograms(args.remote_root)
    # Infrastructure check precedes both the draw and the denominator.
    fixture = ProgramSource(
        kind=ProgramKind.GENERATOR,
        entrypoint="G",
        source="""
class G(Generator):
    def __next__(self):
        return Instance(id='preflight', cell=self.cell, seed=0,
                        spec=self.config['spec'], oracle=self.config['oracle'],
                        provenance=Provenance(generator='G', generator_version='1', seed=0))
""",
    )
    executor.generate(fixture, Cell(levels={}), 0, config, 1)
    model = RecordingModel(
        base_url="http://127.0.0.1:18077/v1",
        model="qwen3-8b",
        version=pin["proposer"]["revision"],
        license=LicenseClass.PERMISSIVE,
        timeout_seconds=180,
    )
    proposer = LLMProposer(model, seed=0)
    critic = StaticCritic(executor=executor, generator_config=config)
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "recorded_before_draw": utc_now().isoformat(),
        "n": 10,
        "decoding_seeds": list(range(10)),
        "identity_pin_sha256": hashlib.sha256(pin_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "context": context.model_dump(mode="json"),
        "context_digest": sha256_json(context.model_dump(mode="json")),
        "remote_root": args.remote_root,
        "server": "worker-5:8077",
        "client": "local via worker-4 SSH tunnel",
        "live_gates": ["schema-v2 parse", "exact seed echo", "confined StaticCritic"],
        "unmeasured_gates": [
            "channel runtime admission",
            "build",
            "gold invariance",
            "protected final oracle",
            "witness",
        ],
        "estimand": "structural acceptance conditional on one fixed mined seed and decoding policy",
        "cp_caveat": "descriptive binomial interval; no corpus representativeness or full-admission claim",
        "api_provider_calls": 0,
    }
    (args.output / "registration.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for index in range(10):
        validate(pin_path)
        proposer.seed = index
        row = {"index": index, "parsed": False, "structural": False, "infrastructure_error": None}
        try:
            draft = proposer.propose(context)
            row["parsed"] = True
            verdict = critic.critique(draft)
            row["critique"] = verdict.model_dump(mode="json")
            row["structural"] = verdict.accepted
            if executor.infrastructure_errors:
                raise RuntimeError(str(executor.infrastructure_errors))
        except ProposalError as exc:
            row["parse_error"] = str(exc)
        except Exception as exc:
            row["infrastructure_error"] = repr(exc)
            row["structural"] = None
        row["request"] = getattr(model, "request_record", None)
        row["completion"] = getattr(model, "completion_record", None)
        rows.append(row)
        with (args.output / "draws.jsonl").open("a") as handle:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
        print(
            json.dumps(
                {k: row[k] for k in ("index", "parsed", "structural", "infrastructure_error")}
            ),
            flush=True,
        )
        if row["infrastructure_error"] is not None:
            break
    completed = len(rows) == 10 and all(r["infrastructure_error"] is None for r in rows)
    k = sum(r["structural"] is True for r in rows)
    result = {
        "completed_registered_draw": completed,
        "planned": 10,
        "attempted": len(rows),
        "parsed": sum(r["parsed"] for r in rows),
        "structural_accepted": k,
        "structural_rate": k / 10 if completed else None,
        "structural_cp95": clopper_pearson(k, 10) if completed else None,
        "full_admission": None,
        "provider_api_calls": 0,
        "refusal": "full admission and target outcomes not measured",
    }
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
