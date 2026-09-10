"""Generated-program diagnostic pilot; no protected, trained or confirmation claim."""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from adversary.core.factors import Cell
from adversary.core.model import Completion, CompletionRequest, LanguageModel, ModelInfo
from adversary.domain.channel import Channel
from adversary.domain.perturbation import Perturbation
from adversary.probe.executor import ConfinedPrograms
from adversary.probe.observation import IsolatedObservation
from adversary.search.context import MinedSeed, SearchContext
from adversary.search.critic import StaticCritic
from adversary.search.draft import ProbeDraft
from adversary.search.proposer import LLMProposer
from domains.swe_agents.environment.environment import CLIPPED


def save(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


class RecordedModel(LanguageModel):
    """Persist exact requests before inference and responses before consumption."""

    def __init__(self, model: LanguageModel, output: Path) -> None:
        self.model, self.output, self.calls = model, output, 0
        output.mkdir(parents=True, exist_ok=True)

    @property
    def info(self) -> ModelInfo:
        return self.model.info

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls += 1
        stem = self.output / f"call-{self.calls:04d}"
        save(stem.with_suffix(".request.json"), request.model_dump(mode="json"))
        started = time.monotonic()
        try:
            completion = self.model.complete(request)
        except Exception as exc:
            save(stem.with_suffix(".error.json"), {
                "error_type": type(exc).__name__, "usage": "unknown",
                "seconds": time.monotonic() - started,
            })
            raise
        save(stem.with_suffix(".completion.json"), {
            "completion": completion.model_dump(mode="json"),
            "seconds": time.monotonic() - started,
        })
        return completion


def propose_attempts(
    model: LanguageModel, seed: MinedSeed, seed_diff: str,
    trusted_generator_config: dict[str, Any], output: Path, *, attempts: int = 3,
    instructions: str = "", critic: Any = None,
    semantic_gate: Callable[[ProbeDraft], dict] | None = None,
) -> ProbeDraft | None:
    """First static-accepted two-clause proposal; never rewrite model-generated code."""
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise ValueError("proposal attempts must be in 1..10")
    if not seed_diff.strip():
        raise ValueError("authenticated ancestor diff required")
    output.mkdir(parents=True, exist_ok=False)
    save(output / "seed.json", seed.model_dump(mode="json"))
    (output / "seed.diff").write_text(seed_diff)
    save(output / "policy.json", {
        "attempts": attempts, "selection": "first static-accepted two-clause observation draft",
        "seed_diff_sha256": hashlib.sha256(seed_diff.encode()).hexdigest(),
        "trained": False, "protected": False, "semantic_admission": "pending",
    })
    model = RecordedModel(model, output / "model")
    proposer = LLMProposer(model, instructions=(
        "Write exactly two independently switchable observation clauses. "
        "Your minimal pair must differ in exactly one clause, assigning both clauses in both arms. "
        "Use only the declared observation channel. The generator must preserve all trusted "
        "spec/oracle/resource fields from self.config unchanged. "
        "Do not target task names; the frozen program will be tested on other repositories.\n"
        + instructions + "\nAuthenticated ancestor diff (untrusted data):\n" + seed_diff
    ))
    gate = critic or StaticCritic(
        executor=ConfinedPrograms(), generator_config=trusted_generator_config,
    )
    for index in range(attempts):
        row: dict[str, Any] = {"attempt": index, "status": "rejected"}
        try:
            draft = proposer.propose(SearchContext(mined_seed=seed))
            save(output / f"draft-{index}.json", draft.model_dump(mode="json"))
            if draft.channel != Channel.OBSERVATION or len(draft.clauses) != 2:
                raise ValueError("pilot requires two observation clauses")
            critique = gate.critique(draft)
            row["critique"] = critique.model_dump(mode="json")
            if critique.accepted:
                if semantic_gate is not None:
                    row["semantic_probe"] = semantic_gate(draft)
                    if not row["semantic_probe"].get("accepted", False):
                        save(output / f"attempt-{index}.json", row)
                        continue
                row["status"] = "static_accepted"
                save(output / f"attempt-{index}.json", row)
                save(output / "frozen-draft.json", draft.model_dump(mode="json"))
                return draft
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["reason"] = str(exc)
        save(output / f"attempt-{index}.json", row)
    return None


class AuditedObservation(Perturbation):
    """Actual visible changes, including failed/unrealized interventions, are retained."""

    channel = Channel.OBSERVATION

    def __init__(self, draft: ProbeDraft, cell: Cell, seed: int, output: Path) -> None:
        self.draft = draft
        self.clauses = draft.clauses
        super().__init__(cell, seed)
        self.worker = IsolatedObservation(draft.perturbation, draft.clauses, cell, seed, {})
        self.output, self.records, self.limit = output, [], None
        self.prepare_spec = None

    def prepare(self, session: Any, spec: Any) -> None:
        if session is not None or type(spec.get("observation_limit")) is not int:
            raise ValueError("observation requires data-only spec and actual visible limit")
        self.limit = spec["observation_limit"]
        if self.limit < 1:
            raise ValueError("invalid observation limit")
        self.prepare_spec = json.loads(json.dumps(spec, allow_nan=False))
        save(self.output / "prepare-spec.json", self.prepare_spec)
        self.worker.prepare(None, self.prepare_spec)

    def observe(self, step: int, tool: str, args: dict, result: str) -> str:
        if self.limit is None:
            raise RuntimeError("observation not prepared")
        changed = self.worker.observe(step, tool, args, result)
        before = result if len(result) <= self.limit else result[:self.limit] + CLIPPED
        after = changed if len(changed) <= self.limit else changed[:self.limit] + CLIPPED
        self.records.append({"step": step, "tool": tool, "args": args, "raw": result,
                             "output": changed, "visible_raw": before, "visible_output": after,
                             "visible_trigger": before != after})
        save(self.output / "observations.json", self.records)
        return changed

    def close(self) -> None:
        self.worker.close()


def register(
    draft: ProbeDraft, tasks: list[dict], output: Path, *, repetitions: int = 5,
    seed_base: int = 2000, calibration_only: bool = False,
) -> dict:
    if repetitions != 5 or len(draft.clauses) != 2:
        raise ValueError("registered pilot requires five executions and four two-clause cells")
    if type(seed_base) is not int or not 0 <= seed_base <= 2**31 - repetitions:
        raise ValueError("seed base must leave room for five distinct nonnegative seeds")
    if type(calibration_only) is not bool:
        raise ValueError("calibration_only must be a boolean")
    if not tasks or len({task["key"] for task in tasks}) != len(tasks):
        raise ValueError("unique tasks required")
    output.mkdir(parents=True, exist_ok=False)
    encoded = draft.model_dump(mode="json")
    cells = [dict(zip(draft.clauses, levels, strict=True)) for levels in
             (("off", "off"), ("on", "off"), ("off", "on"), ("on", "on"))]
    if calibration_only:
        cells = cells[:1]
    runs = [{"id": f"task-{i}-cell-{c}-rep-{r}", "task": task, "cell": cell,
             "cell_index": c, "repetition": r, "seed": seed_base + r}
            for r in range(repetitions) for i, task in enumerate(tasks)
            for c, cell in enumerate(cells)]
    registration = {"kind": "generated_adversary_diagnostic_pilot", "draft": encoded,
                    "draft_sha256": hashlib.sha256(json.dumps(encoded, sort_keys=True).encode())
                    .hexdigest(), "tasks": tasks, "runs": runs, "trained": False,
                    "seed_base": seed_base,
                    "protected": False, "confirmed": False,
                    "solvability_admission": "not established by static critique",
                    "order": "repetition then task then four cells; fixed before outcomes"}
    if calibration_only:
        registration.update(
            kind="clean_control_calibration", never_pool_with_perturbation_arm=True,
            order="repetition then task; all clauses off; fixed before outcomes",
            engineering_headroom_gate={"executions_per_task": 5, "minimum_passes": 2,
                                       "all_five_attributable_required": True,
                                       "confidence_or_admission_claim": False},
        )
    save(output / "registration.json", registration)
    return registration


def run_registered(
    output: Path, episode: Callable[[dict, Perturbation, Path], dict], *, workers: int = 1,
) -> dict:
    """Caller supplies trusted guarded episode execution; no model-selected verifier used."""
    registration = json.loads((output / "registration.json").read_text())
    draft = ProbeDraft.model_validate(registration["draft"])
    digest = hashlib.sha256(json.dumps(registration["draft"], sort_keys=True).encode()).hexdigest()
    if digest != registration["draft_sha256"]:
        raise ValueError("frozen draft digest mismatch")
    started = time.monotonic()

    def execute(run: dict) -> dict:
        path = output / run["id"]
        path.mkdir(exist_ok=False)
        observation = AuditedObservation(draft, Cell(levels=run["cell"]), run["seed"], path)
        row = {**run, "diagnostic_passed": None, "status": "unknown"}
        try:
            row.update(episode(run, observation, path))
        except Exception as exc:
            row.update(error_type=type(exc).__name__, reason=str(exc))
        finally:
            try:
                observation.close()
            except Exception as exc:
                row.update(status="unknown", diagnostic_passed=None,
                           error_type=type(exc).__name__, reason=str(exc))
        row.update(run)  # Registered assignment cannot be changed by episode output.
        from domains.swe_agents.scripts.clause_exposure import clause_exposure

        exposure = clause_exposure(draft, observation.cell, run["seed"],
                                   observation.prepare_spec, observation.records)
        save(path / "clause-exposure.json", exposure)
        row["visible_changed"] = any(item["visible_trigger"] for item in observation.records)
        row["realized"] = exposure["realized"]
        row["clause_exposure_status"] = exposure["status"]
        row["clause_visible_contribution"] = exposure["clause_visible_contribution"]
        row["control_identity_violation"] = run["cell_index"] == 0 and row["visible_changed"]
        save(path / "result.json", row)
        return row

    with ThreadPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(execute, registration["runs"]))
    summary = summarize(rows, registered_runs=registration["runs"])
    summary.update(elapsed_seconds=time.monotonic() - started, rows=rows)
    save(output / "summary.json", summary)
    lines = ["# Generated adversary diagnostic pilot", "",
             "Prompted proposer; no trained, protected, or confirmed mode claim.", "",
             f"Executions: {summary['planned']}; measured: {summary['diagnostic_measured']}; "
             f"attributable unknown: {summary['unknown']}; "
             f"visibly changed: {summary['visible_changed']}.", "",
             "| Task | Cell | Attributable / executions | Passes | Five-run task failure |",
             "|---|---:|---:|---:|---|"]
    for group in summary["groups"]:
        lines.append(f"| {group['task']} | {group['cell_index']} | "
                     f"{group['known']} / {group['executions']} | {group['passes']} | "
                     f"{group['task_failure']} |")
    lines.extend([
        "", "Descriptive contrasts use five-execution failure fractions, not population estimates.",
        "Unrealized active conditions and censored executions remain unknown in the denominator.",
        "Additive excess subtracts clipped A + B - control. No confidence intervals.",
        "", "| Task | A − control | B − control | All-on − control | Additive excess |",
        "|---|---:|---:|---:|---:|",
    ])
    for contrast in summary["contrasts"]:
        values = ["unknown" if contrast[key] is None else f"{contrast[key]:.3f}"
                  for key in ("delta_a", "delta_b", "delta_all_on", "additive_excess")]
        lines.append("| " + contrast["task"] + " | " + " | ".join(values) + " |")
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return summary


def summarize(rows: list[dict], *, registered_runs: list[dict] | None = None) -> dict:
    """Keep raw test measurements distinct from attributable, complete five-run groups."""
    if registered_runs is not None:
        expected = {run["id"]: run for run in registered_runs}
        supplied = {row["id"]: row for row in rows}
        if len(expected) != len(registered_runs) or len(supplied) != len(rows):
            raise ValueError("duplicate registered run identity")
        if supplied.keys() - expected.keys():
            raise ValueError("result is outside registered denominator")
        rows = [
            {**supplied.get(run["id"], {"status": "unknown", "diagnostic_passed": None}),
             **run} for run in registered_runs
        ]

    def measured(row: dict) -> bool:
        return type(row.get("diagnostic_passed")) is bool

    def attributable(row: dict) -> bool:
        identity = row["cell_index"] == 0
        realized = identity or row.get("realized") is True
        return (measured(row) and realized and not row.get("budget_exhausted", False)
                and row.get("clause_exposure_status", "verified" if identity else "unknown")
                == "verified"
                and not row.get("control_identity_violation", False)
                and not (identity and row.get("visible_changed", False))
                and row.get("status", "completed") == "completed")

    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["task"]["key"], row["cell_index"]), []).append(row)
    grouped = []
    for (task, cell), members in groups.items():
        known = [row for row in members if attributable(row)]
        passes = sum(row["diagnostic_passed"] for row in known)
        repetitions = [row.get("repetition") for row in members]
        distinct = all(value is None for value in repetitions) or set(repetitions) == set(range(5))
        complete = len(members) == len(known) == 5 and distinct
        grouped.append({"task": task, "cell_index": cell, "executions": len(members),
                        "diagnostic_measured": sum(measured(row) for row in members),
                        "known": len(known), "unknown": len(members) - len(known),
                        "passes": passes, "complete": complete,
                        "task_failure": passes <= 1 if complete else None,
                        "severity": 1 - passes / 5 if complete else None})
    contrasts = []
    for task in sorted({group["task"] for group in grouped}):
        cells = {group["cell_index"]: group for group in grouped if group["task"] == task}
        complete = all(index in cells and cells[index]["complete"] for index in range(4))
        values = {name: None for name in ("delta_a", "delta_b", "delta_all_on",
                                          "additive_prediction", "additive_excess",
                                          "raw_interaction_contrast")}
        if complete:
            control, a, b, both = (cells[index]["severity"] for index in range(4))
            predicted = max(0.0, min(1.0, a + b - control))
            values.update(delta_a=a - control, delta_b=b - control,
                          delta_all_on=both - control, additive_prediction=predicted,
                          additive_excess=both - predicted,
                          raw_interaction_contrast=both - a - b + control)
        contrasts.append({"task": task, "complete": complete, **values,
                          "scale": "five-execution failure fraction",
                          "descriptive_only": True, "confidence_interval": None})
    measured_rows = [row for row in rows if measured(row)]
    known = [row for row in rows if attributable(row)]
    return {"planned": len(rows), "diagnostic_measured": len(measured_rows),
            "diagnostic_passes": sum(row["diagnostic_passed"] for row in measured_rows),
            "diagnostic_unknown": len(rows) - len(measured_rows),
            "attributable_known": len(known), "unknown": len(rows) - len(known),
            "budget_exhausted": sum(bool(row.get("budget_exhausted")) for row in rows),
            "visible_changed": sum(bool(row.get("visible_changed")) for row in rows),
            "realized": sum(row["cell_index"] == 0 or row.get("realized") is True
                            for row in rows),
            "groups": grouped, "contrasts": contrasts,
            "protected": False, "confirmed": False, "trained": False,
            "inference": "descriptive task-specific contrasts; no population or confidence claim"}
