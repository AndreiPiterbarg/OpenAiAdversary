"""Deterministic trace-only clause exposure; never estimates counterfactual task outcomes."""

from __future__ import annotations

from typing import Any

from adversary.core.factors import Cell
from adversary.probe.observation import IsolatedObservation
from domains.swe_agents.environment.environment import CLIPPED


def clause_exposure(draft: Any, cell: Cell, seed: int, spec: dict[str, Any] | None,
                    records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "deterministic_recorded_trace_clause_exposure_v1", "status": "unknown",
        "realized": False, "actual_replay_matches": False,
        "active_clauses": [name for name in draft.clauses if cell[name] == "on"],
        "clause_visible_contribution": {}, "visible_changed": False,
        "counterfactual_outcome_claim": False,
    }
    try:
        if spec is None or type(spec.get("observation_limit")) is not int:
            raise ValueError("missing exact preparation spec")
        limit = spec["observation_limit"]
        if limit < 1:
            raise ValueError("invalid visible observation limit")

        def visible(text: str) -> str:
            return text if len(text) <= limit else text[:limit] + CLIPPED

        def replay(levels: dict[str, str]) -> list[str]:
            worker = IsolatedObservation(draft.perturbation, draft.clauses,
                                         Cell(levels=levels), seed, {})
            try:
                worker.prepare(None, spec)
                return [worker.observe(row["step"], row["tool"], row["args"], row["raw"])
                        for row in records]
            finally:
                worker.close()

        actual = replay(dict(cell.levels))
        if any(output != row["output"] or visible(output) != row["visible_output"]
               or visible(row["raw"]) != row["visible_raw"]
               for output, row in zip(actual, records, strict=True)):
            raise ValueError("actual-cell replay differs from recorded output")
        result["actual_replay_matches"] = True
        changed = [visible(output) != visible(row["raw"])
                   for output, row in zip(actual, records, strict=True)]
        result["visible_changed"] = any(changed)
        contributions = {}
        for name in result["active_clauses"]:
            levels = dict(cell.levels)
            levels[name] = "off"
            ablated = replay(levels)
            indices = [
                index for index, (left, right) in enumerate(zip(actual, ablated, strict=True))
                if changed[index] and visible(left) != visible(right)
            ]
            contributions[name] = {"exposed": bool(indices), "observation_indices": indices}
        result["clause_visible_contribution"] = contributions
        identity = not result["active_clauses"]
        if identity and any(changed):
            raise ValueError("inactive control changed visible observations")
        result.update(status="verified", realized=(not any(changed) if identity else
                      all(value["exposed"] for value in contributions.values())))
    except Exception as exc:
        result.update(error_type=type(exc).__name__, reason=str(exc))
    return result
