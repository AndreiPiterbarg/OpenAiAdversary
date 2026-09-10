"""What each envelope level means for the plugin: selected from the pool, set on the harness,
or injected as an event.

Family A levels are *selected for*: the task pool records the full-envelope level of every
measured property per instance, and a cell is realised by choosing instances whose properties
match. The pilot envelope re-discretises some of those factors, so a pilot level maps onto a
set of full-envelope levels. Family B conditions are harness settings written into the task
spec. Family B events are injected hazards.
"""

from enum import StrEnum
from typing import Final

from adversary.core.factors import Cell


class Realisation(StrEnum):
    """How the plugin realises a factor."""

    POOL = "pool"
    """Selected: pick task instances whose measured property has the level."""

    SETTING = "setting"
    """Set: a harness or deployment setting in the task spec."""

    EVENT = "event"
    """Injected: a hazard scheduled during the episode."""

    DERIVED = "derived"
    """Meaningful only in combination with an event (step position)."""


REALISATION: Final[dict[str, Realisation]] = {
    # Family A: all selected from the pool.
    "language": Realisation.POOL,
    "library_version_pin": Realisation.POOL,
    "api_surface_changed": Realisation.POOL,
    "dependency_depth": Realisation.POOL,
    "transitive_conflict": Realisation.POOL,
    "repo_shape": Realisation.POOL,
    "build_system": Realisation.POOL,
    "test_runner": Realisation.POOL,
    "test_flakiness": Realisation.POOL,
    "test_coverage_of_touched_code": Realisation.POOL,
    "lockfile_state": Realisation.POOL,
    "codebase_size": Realisation.POOL,
    "linter_conventions": Realisation.POOL,
    "type_checking": Realisation.POOL,
    "native_dependencies": Realisation.POOL,
    "non_english_identifiers": Realisation.POOL,
    "deprecated_api_in_repo": Realisation.POOL,
    "ambiguous_fix_locus": Realisation.POOL,
    "fix_requires_config": Realisation.POOL,
    "git_history_contains_answer": Realisation.SETTING,
    # Family B.
    "stale_tool_spec": Realisation.EVENT,
    "observation_limit": Realisation.SETTING,
    "transient_failure": Realisation.POOL,
    "silently_wrong_output": Realisation.EVENT,
    "cross_source_conflict": Realisation.POOL,
    "memory_drift": Realisation.EVENT,
    "hazard_step_position": Realisation.DERIVED,
    "policy_constraint": Realisation.SETTING,
    "constraint_entanglement": Realisation.SETTING,
    "context_length": Realisation.SETTING,
    "prior_wrong_assertion": Realisation.EVENT,
    "task_length": Realisation.POOL,
    "environment_nondeterminism": Realisation.POOL,
    "issue_underspecified": Realisation.POOL,
    "issue_false_premise": Realisation.POOL,
    "tool_set": Realisation.SETTING,
    "budget_pressure": Realisation.SETTING,
    "misleading_docs": Realisation.POOL,
    "misleading_errors": Realisation.EVENT,
    "interrupted_session": Realisation.SETTING,
    "multi_agent_handoff": Realisation.SETTING,
    "self_report_required": Realisation.SETTING,
    "rollback_required": Realisation.POOL,
}

# Pilot levels that merge full-envelope levels.
LEVEL_ALIASES: Final[dict[tuple[str, str], frozenset[str]]] = {
    ("test_coverage_of_touched_code", "uncovered"): frozenset({"none"}),
    ("test_coverage_of_touched_code", "covered"): frozenset({"partial", "high"}),
    ("type_checking", "not_enforced"): frozenset({"absent"}),
    ("type_checking", "enforced"): frozenset({"present", "strict"}),
}


def pool_levels(factor: str, level: str) -> frozenset[str]:
    """Full-envelope levels a cell level matches when selecting from the pool."""
    return LEVEL_ALIASES.get((factor, level), frozenset({level}))


def pool_factors(cell: Cell) -> dict[str, frozenset[str]]:
    """The pool-selected part of a cell as ``property -> acceptable levels``."""
    return {
        f: pool_levels(f, lv) for f, lv in cell.items() if REALISATION.get(f) is Realisation.POOL
    }


def event_factors(cell: Cell) -> dict[str, str]:
    """Factors realised by injection that the cell switches on."""
    return {
        f: lv
        for f, lv in cell.items()
        if REALISATION.get(f) is Realisation.EVENT and lv not in ("absent", "no", "none")
    }
