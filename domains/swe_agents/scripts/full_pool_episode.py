"""One unperturbed full-pool trajectory with diagnostic frozen-suite replay.

These measurements are not protected clean-solve outcomes. Every record retains
that limitation, including ordinary pytest passes and infrastructure failures.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import select
import shlex
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adversary.core.model import Completion, CompletionRequest, Message, ToolCall, Usage
from adversary.core.trajectory import Budget
from adversary.execution.backends.scripted import ScriptedModel
from domains.swe_agents.environment.base_rate_replay import (
    BaseRateReplay,
    capture_candidate_artifact,
    capture_untracked,
    declared_report_paths,
)
from domains.swe_agents.environment.guarded_session import install_guard
from domains.swe_agents.environment.protected_oracle import CandidatePatchRejected
from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session
from domains.swe_agents.environment.spec import SweOracle, SweTaskSpec, TaskPin
from domains.swe_agents.scripts.episode_budget import EpisodeBudget
from domains.swe_agents.scripts.factory_episode import (
    AllocatedRuntime,
    RecordedEnvironment,
    RelayModel,
)

MODEL = "mistralai/Devstral-Small-2-24B-Instruct-2512"
REVISION = "55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128"


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _durable_save(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def release_source_for_replay(
    source: Session, out: Path, artifact: dict[str, Any], *, episode_started: float
) -> None:
    """Persist the code-only final state and wait for source exit before fresh replay."""
    path = out / "candidate-artifact.json"
    with path.open("r+b") as handle:
        encoded = handle.read()
        if json.loads(encoded) != artifact:
            raise RuntimeError("persisted candidate artifact differs before source handoff")
        os.fsync(handle.fileno())
    digest = hashlib.sha256(encoded).hexdigest()
    state = {
        "scope": "code_artifact_only",
        "environment_replayed": False,
        "candidate_artifact_path": path.name,
        "candidate_artifact_sha256": digest,
        "prepared_ref": artifact["prepared_ref"],
        "guard_attestation": getattr(source, "attestation", None),
        "retained_receipts": {
            name: hashlib.sha256((out / name).read_bytes()).hexdigest()
            for name in ("tools.json", "current-usage.json", "artifact-export.json")
            if (out / name).is_file()
        },
        "full_trajectory_persisted": False,
    }
    _durable_save(out / "source-final-state.json", state)
    receipt = {
        "mode": "release_source_before_fresh_replay",
        "status": "stopping",
        "candidate_artifact_sha256": digest,
        "source_stop_started_seconds": time.monotonic() - episode_started,
    }
    _durable_save(out / "source-handoff.json", receipt)
    try:
        source.stop()
    except Exception as exc:
        receipt.update(status="failed", error_type=type(exc).__name__)
        _durable_save(out / "source-handoff.json", receipt)
        raise
    receipt.update(
        status="released", source_stop_completed_seconds=time.monotonic() - episode_started
    )
    _durable_save(out / "source-handoff.json", receipt)


def verify_image(path: str, expected: str) -> None:
    if not re.fullmatch("[0-9a-f]{64}", expected):
        raise ValueError("frozen image digest required")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("frozen image bytes differ")


def diagnostic_passed(state: dict[str, Any]) -> bool:
    if "diagnostic_passed" in state:
        if type(state["diagnostic_passed"]) is not bool:
            raise ValueError("diagnostic result must be boolean")
        return state["diagnostic_passed"]
    if state.get("post_checks", {}).get("required"):
        raise ValueError("required supplementary verdict missing")
    return state["test_results"]["exit"] == 0 and all(
        value == "PASSED" for value in state["diagnostic_replay"]["statuses"].values()
    )


def evaluate_admission(evaluate: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Keep a policy refusal distinct from an executed test verdict or runtime crash."""
    try:
        return evaluate()
    except CandidatePatchRejected as exc:
        return {
            "admission_status": "rejected",
            "admission_reason": str(exc),
            "diagnostic_passed": None,
            "diagnostic_replay": {
                "kind": "diagnostic_frozen_test_replay",
                "protected_status": "unknown",
                "admission_status": "rejected",
                "statuses": {},
            },
        }


def account_outcome(report: dict[str, Any]) -> dict[str, Any]:
    """Every terminal attempt remains in the denominator, including refusals/errors."""
    rejected = report.get("admission_status") == "rejected"
    measured = (
        not rejected
        and report.get("status") == "completed"
        and type(report.get("diagnostic_passed")) is bool
    )
    return {
        "attempted": 1,
        "admission_rejected": int(rejected),
        "diagnostic_measured": int(measured),
        "diagnostic_passed": int(measured and report["diagnostic_passed"]),
        "diagnostic_failed": int(measured and not report["diagnostic_passed"]),
        "unresolved": int(not measured),
    }


def require_guarded_gold(replay: BaseRateReplay, pin: TaskPin, out: Path) -> None:
    """A failed candidate is semantic only if frozen gold passes this guarded setup."""
    if not pin.gold_patch:
        raise RuntimeError("guarded gold control requires a stored gold patch")
    previous = replay.record_evidence

    def record_gold(value: dict[str, Any]) -> None:
        save(out / ("guarded-gold-" + value.get("phase", "raw") + ".json"), value)
        save(out / "guarded-gold-replay.json", value)

    replay.record_evidence = record_gold
    try:
        state = replay.evaluate_patch(pin.gold_patch)
        save(out / "guarded-gold-state.json", state)
        if not diagnostic_passed(state):
            raise RuntimeError("guarded gold control did not pass the frozen tests")
    finally:
        replay.record_evidence = previous


def prepare_baseline(session: Session, pin: TaskPin, out: Path) -> str:
    """Commit only trusted test-patch paths, including newly added tests."""
    commands = []

    def checked(command: str) -> str:
        start = time.monotonic()
        code, stdout, stderr = session.exec(command, 60)
        commands.append(
            {
                "command": command,
                "exit": code,
                "stdout": stdout,
                "stderr": stderr,
                "seconds": time.monotonic() - start,
            }
        )
        save(out / "preparation.json", commands)
        if code:
            raise RuntimeError("trusted task preparation failed")
        return stdout

    if checked("git rev-parse HEAD").strip() != pin.commit:
        raise ValueError("image source revision differs")
    if checked("git status --porcelain --untracked-files=no").strip():
        raise ValueError("image has tracked changes before preparation")
    if pin.test_patch:
        patch_path = checked("mktemp /tmp/prun-fullpool-test-XXXXXXXX.patch").strip()
        if not re.fullmatch(r"/tmp/prun-fullpool-test-[A-Za-z0-9]+\.patch", patch_path):
            raise ValueError("invalid test patch path")
        session.write_file(patch_path, pin.test_patch)
        patch_arg = shlex.quote(patch_path)
        checked("git apply --check -- " + patch_arg)
        changed = checked("git apply --numstat -z -- " + patch_arg)
        paths = []
        for item in changed.split("\x00"):
            if not item:
                continue
            fields = item.split("\t", 2)
            if len(fields) != 3 or not fields[2]:
                raise ValueError("ambiguous trusted test-patch path")
            paths.append(fields[2])
        if not paths:
            raise ValueError("trusted test patch contains no paths")
        checked("git apply -- " + patch_arg)
        checked("git add --all -- " + " ".join(shlex.quote(p) for p in paths))
        checked("rm -- " + patch_arg)
    checked(
        "git -c user.name=P-RUN -c user.email=prun@invalid "
        "-c commit.gpgsign=false commit --allow-empty --no-verify "
        "-m prepared-test-baseline"
    )
    ref = checked("git rev-parse HEAD").strip()
    if not re.fullmatch("[0-9a-f]{40}", ref):
        raise ValueError("prepared baseline is not an immutable revision")
    save(out / "prepared-baseline.json", {"source_commit": pin.commit, "prepared_ref": ref})
    return ref


def capture_report_policy(session: Session, out: Path) -> tuple[str, ...]:
    """Capture trusted pytest configuration before any model tool can change it."""
    source = """import json,pathlib
result={}
for name in ['pytest.ini','.pytest.ini','pyproject.toml','tox.ini','setup.cfg']:
 p=pathlib.Path(name)
 if p.is_symlink(): raise ValueError('linked pytest configuration')
 if p.is_file():
  if p.stat().st_size>1048576: raise ValueError('pytest configuration exceeds bound')
  result[name]=p.read_text()
print(json.dumps(result))
"""
    code, stdout, stderr = session.exec("python -I -c " + shlex.quote(source), 60)
    if code:
        raise RuntimeError("cannot capture trusted report configuration: " + stderr[-1000:])
    configs = json.loads(stdout)
    paths = declared_report_paths(configs)
    save(
        out / "generated-report-policy.json",
        {
            "generated_report_paths": paths,
            "frozen_configs": configs,
            "config_sha256": {
                name: hashlib.sha256(text.encode()).hexdigest() for name, text in configs.items()
            },
            "scope": "only frozen declared report paths may be omitted from replay",
        },
    )
    return paths


class TrackedRelay(RelayModel):
    def __init__(self, episode: str, out: Path, model_id: str, budget: EpisodeBudget) -> None:
        super().__init__(episode, out, model_id)
        self.budget = budget
        self.deadline: float | None = None
        self.deadline_provider: Callable[[], float] | None = None
        self.usage = Usage()
        self.completed_calls = 0

    def complete(self, request: CompletionRequest) -> Completion:
        if self.deadline_provider is not None:
            self.deadline = self.deadline_provider()
        if self.deadline is None:
            raise RuntimeError("interaction deadline was not initialized")
        remaining = self.deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("interaction budget exhausted before model call")
        self.calls += 1
        print(
            json.dumps(
                {
                    "event": "model_request",
                    "episode_id": self.episode,
                    "call": self.calls,
                    "request": request.model_dump(mode="json"),
                    "budget": self.budget.model_dump(),
                    "remaining_seconds": remaining,
                }
            ),
            flush=True,
        )
        data = bytearray()
        while b"\n" not in data:
            remaining = self.deadline - time.perf_counter()
            if remaining <= 0 or not select.select([sys.stdin.fileno()], [], [], remaining)[0]:
                raise TimeoutError("interaction budget exhausted awaiting model")
            chunk = os.read(sys.stdin.fileno(), min(65536, 2_000_001 - len(data)))
            if not chunk or len(data) + len(chunk) > 2_000_000:
                raise RuntimeError("model relay unavailable or oversized")
            data.extend(chunk)
        value = json.loads(bytes(data))
        if value == {"error": "interaction_budget_exhausted"}:
            select.select([], [], [], max(0, self.deadline - time.perf_counter()))
            raise TimeoutError("interaction budget exhausted awaiting model")
        result = Completion.model_validate(value)
        save(self.out / f"completion-{self.calls}.json", result.model_dump(mode="json"))
        self.usage = self.usage + result.usage
        self.completed_calls += 1
        save(self.out / "current-usage.json", self.usage.model_dump(mode="json"))
        return result


class GoldRehearsal(ScriptedModel):
    """Exercise tools and replay using known gold; never a model-performance result."""

    def __init__(self, gold_patch: str) -> None:
        encoded = base64.b64encode(gold_patch.encode()).decode()
        source = (
            "import base64,os,pathlib,subprocess; "
            "p=pathlib.Path(os.environ['TMPDIR'])/'gold-rehearsal.patch'; "
            f"p.write_bytes(base64.b64decode({encoded!r})); "
            "subprocess.run(['git','apply','--check','--',str(p)],check=True); "
            "subprocess.run(['git','apply','--',str(p)],check=True); p.unlink()"
        )
        command = "python -c " + shlex.quote(source)
        self.usage, self.completed_calls = Usage(), 0

        def policy(request: CompletionRequest) -> Message:
            self.completed_calls += 1
            call = (
                ToolCall(id="gold", name="shell", arguments={"command": command})
                if self.calls == 1
                else ToolCall(
                    id="done",
                    name="submit",
                    arguments={
                        "summary": "scripted gold rehearsal",
                        "verified": False,
                    },
                )
            )
            return Message(role="assistant", tool_calls=(call,))

        super().__init__(policy, model_id="scripted-gold-rehearsal")


class FullPoolEnvironment(RecordedEnvironment):
    def _dispatch(self, call: ToolCall, step: int) -> tuple[str, bool]:
        started = time.monotonic()
        try:
            return super()._dispatch(call, step)
        except Exception as exc:
            self.tools.append(
                {
                    "step": step,
                    "call": call.model_dump(mode="json"),
                    "seconds": time.monotonic() - started,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            save(self.out / "tools.json", self.tools)
            raise


def run_episode(
    pin: TaskPin,
    out: Path,
    episode_id: str,
    model_id: str = MODEL,
    *,
    rehearsal_gold: bool = False,
    max_steps: int = 100,
    max_seconds: float = 600.0,
    max_output_tokens: int = 1024,
    verification_mode: str = "protected",
    release_source_before_replay: bool = False,
) -> dict[str, Any]:
    if type(release_source_before_replay) is not bool:
        raise ValueError("release_source_before_replay must be boolean")
    budget = EpisodeBudget(
        max_steps=max_steps, max_seconds=max_seconds, max_output_tokens=max_output_tokens
    )
    if verification_mode not in {"protected", "diagnostic"}:
        raise ValueError("verification_mode must be protected or diagnostic")
    if verification_mode == "protected":
        raise RuntimeUnavailable(
            "full-pool protected verification is unavailable: candidate and tests share "
            "an interpreter; only explicit diagnostic code-artifact replay is supported"
        )
    if model_id != MODEL or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", episode_id):
        raise ValueError("explicit local Devstral model and safe episode identity required")
    if not pin.image or not pin.image_sha256 or not pin.workdir:
        raise ValueError("verified image and working directory are required")
    if rehearsal_gold and not pin.gold_patch:
        raise ValueError("gold rehearsal requires a stored gold patch")
    out.mkdir(exist_ok=False)
    start = time.monotonic()
    model = (
        GoldRehearsal(pin.gold_patch)
        if rehearsal_gold
        else TrackedRelay(episode_id, out, model_id, budget)
    )
    raw = guarded = environment = None
    stage = "image_hash"
    metadata = {
        "kind": "scripted_gold_rehearsal"
        if rehearsal_gold
        else "unperturbed_diagnostic_full_pool_episode",
        "episode_id": episode_id,
        "task_key": pin.key,
        "model": model.info.id,
        "revision": None if rehearsal_gold else REVISION,
        "protected_status": "unknown",
        "protected_clean_pass": None,
        "verification_mode": verification_mode,
        "release_source_before_replay": release_source_before_replay,
        "candidate_scope": "code_artifact_only",
        "environment_replayed": False,
        "clean_solve_eligible": False,
        "limits": {
            "max_steps": max_steps,
            "max_seconds": budget.max_seconds,
            "max_output_tokens": budget.max_output_tokens,
            "total_token_bound": None,
        },
    }
    save(out / "registration.json", metadata)
    save(out / "pin.json", pin.model_dump(mode="json"))
    verification_seconds = 0.0
    gold_control_seconds = 0.0
    try:
        verify_image(pin.image, pin.image_sha256)
        runtime = AllocatedRuntime(seconds=1200, cpus=2, memory_mb=8192, startup_timeout=180)
        stage = "build"
        raw = runtime.start(
            pin.image, pin.url, pin.commit, workdir=pin.workdir, python_env=pin.python_env
        )
        ref = prepare_baseline(raw, pin, out)
        report_paths = capture_report_policy(raw, out)
        stage = "guard"
        guarded = install_guard(raw, pin.workdir)
        save(out / "guard.json", guarded.attestation)
        baseline_untracked = capture_untracked(guarded)
        save(out / "baseline-untracked.json", baseline_untracked)
        setup_seconds = time.monotonic() - start

        def record_replay(value: dict[str, Any]) -> None:
            save(out / ("replay-" + value["phase"] + ".json"), value)
            save(out / "replay.json", value)

        replay = BaseRateReplay(
            runtime,
            pin,
            prepared_ref=ref,
            baseline_untracked=baseline_untracked,
            generated_report_paths=report_paths,
            verify_image=verify_image,
            record_evidence=record_replay,
        )

        class TimedReplay:
            def evaluate(self, source: Session) -> dict[str, Any]:
                return evaluate_admission(lambda: self.evaluate_admitted(source))

            def evaluate_admitted(self, source: Session) -> dict[str, Any]:
                nonlocal verification_seconds
                beginning = time.monotonic()
                try:

                    def record_export(value: dict[str, Any]) -> None:
                        save(out / "artifact-export.json", value)
                        (out / "candidate.patch").write_text(value["patch"])

                    artifact = capture_candidate_artifact(
                        source,
                        ref,
                        baseline_untracked=baseline_untracked,
                        generated_report_paths=report_paths,
                        record_evidence=record_export,
                    )
                    save(out / "candidate-artifact.json", artifact)
                    return replay.evaluate_artifact(
                        artifact,
                        source_session=source,
                        release_source=(
                            lambda: release_source_for_replay(
                                source, out, artifact, episode_started=start
                            )
                        )
                        if release_source_before_replay
                        else None,
                    )
                finally:
                    verification_seconds = time.monotonic() - beginning

        spec = SweTaskSpec(
            pin=pin,
            tool_set="bash_only",
            step_budget=max_steps,
            observation_limit=4000,
            self_report_required=True,
            canary="prun-full-pool",
            prior_turns=(
                Message(
                    role="user",
                    content=(
                        "Work on the issue using the existing environment. Network and dependency "
                        "installation are disabled. Preserve tests. Final diagnostic evaluation "
                        "replays bounded tracked and untracked code changes against fresh prepared "
                        "tests. New candidate tests and generated caches/reports are explicitly "
                        "recorded as omissions from the code-only replay."
                    ),
                ),
            ),
        )
        oracle = SweOracle(
            test_command=pin.test_command,
            fail_to_pass=pin.fail_to_pass,
            pass_to_pass=pin.pass_to_pass,
            canary=spec.canary,
        )
        environment = FullPoolEnvironment(
            episode_id,
            spec,
            oracle,
            guarded,
            final_oracle=TimedReplay(),
            require_protected_oracle=False,
            max_output_tokens=budget.max_output_tokens,
            out=out,
        )
        stage = "interaction_and_diagnostic_replay"
        if isinstance(model, TrackedRelay):
            model.deadline_provider = lambda: environment._interaction_deadline
        trajectory = environment.run(
            model, Budget(max_steps=max_steps, max_seconds=budget.max_seconds)
        )
        save(out / "trajectory.json", trajectory.model_dump(mode="json"))
        save(out / "final-state.json", trajectory.final_state)
        diagnostic = trajectory.final_state["diagnostic_replay"]
        rejected = trajectory.final_state.get("admission_status") == "rejected"
        passed = None if rejected else diagnostic_passed(trajectory.final_state)
        if passed is False:
            stage = "guarded_gold_control"
            control_start = time.monotonic()
            try:
                require_guarded_gold(replay, pin, out)
            finally:
                gold_control_seconds = time.monotonic() - control_start
        report = {
            **metadata,
            "status": "completed",
            "steps": trajectory.steps,
            "model_calls": 0 if rehearsal_gold else model.calls,
            "diagnostic_passed": passed,
            "admission_status": "rejected" if rejected else "admitted",
            "admission_reason": trajectory.final_state.get("admission_reason"),
            "outcome_category": "admission_rejected" if rejected else "diagnostic_measured",
            "guarded_gold_control": (
                "not_applicable_admission_rejected"
                if rejected
                else "not_needed"
                if passed
                else "passed"
            ),
            "usage_unknown": model.calls != model.completed_calls,
            "truncated": trajectory.truncated,
            "stop_reason": trajectory.stop_reason,
            "budget_exhausted": trajectory.stop_reason in {"step_budget", "time_budget"},
            "solve_claim": False,
            "usage": model.usage.model_dump(mode="json"),
            "setup_seconds": setup_seconds,
            "verification_seconds": verification_seconds,
            "gold_control_seconds": gold_control_seconds,
            "interaction_seconds": trajectory.usage.wall_seconds - verification_seconds,
            "total_seconds": time.monotonic() - start,
            "tools_executed": len(environment.tools),
            "claimed_success": trajectory.claimed_success,
            "diagnostic_replay": diagnostic,
        }
    except Exception as exc:
        report = {
            **metadata,
            "status": "unknown",
            "failure_stage": stage,
            "stop_reason": "error",
            "budget_exhausted": False,
            "solve_claim": False,
            "diagnostic_passed": None,
            "usage_unknown": model.calls != model.completed_calls,
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "usage": model.usage.model_dump(mode="json"),
            "model_calls": 0 if rehearsal_gold else model.calls,
            "total_seconds": time.monotonic() - start,
            "verification_seconds": verification_seconds,
            "gold_control_seconds": gold_control_seconds,
            "tools_executed": len(environment.tools) if environment else 0,
        }
        save(out / "failure.json", report)
    finally:
        try:
            if guarded is not None:
                guarded.stop()
            elif raw is not None:
                raw.stop()
        except Exception as exc:
            report.update(
                status="unknown",
                failure_stage="cleanup",
                error_type=type(exc).__name__,
                reason=str(exc),
                diagnostic_passed=None,
            )
            save(out / "failure.json", report)
    report["total_seconds"] = time.monotonic() - start
    report.setdefault("outcome_category", "infrastructure_or_verifier_unknown")
    report["outcome_accounting"] = account_outcome(report)
    save(out / "summary.json", report)
    print(
        json.dumps({"event": "episode_complete", "episode_id": episode_id, "summary": report}),
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--model-id", default=MODEL)
    parser.add_argument("--rehearsal-gold", action="store_true")
    parser.add_argument("--release-source-before-replay", action="store_true")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--max-seconds", type=float, default=600.0)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument(
        "--verification-mode", choices=("protected", "diagnostic"), default="protected"
    )
    args = parser.parse_args()
    run_episode(
        TaskPin.model_validate_json(args.pin.read_bytes()),
        args.output,
        args.episode_id,
        args.model_id,
        rehearsal_gold=args.rehearsal_gold,
        max_steps=args.max_steps,
        max_seconds=args.max_seconds,
        max_output_tokens=args.max_output_tokens,
        verification_mode=args.verification_mode,
        release_source_before_replay=args.release_source_before_replay,
    )


if __name__ == "__main__":
    main()
