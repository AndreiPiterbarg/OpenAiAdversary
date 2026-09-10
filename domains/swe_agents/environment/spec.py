"""What the target sees (:class:`SweTaskSpec`) and what the verifier sees (:class:`SweOracle`),
and the pool of real task instances both are built from."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.licensing import SourceNotice
from adversary.core.model import Message
from adversary.probe.program import ProgramSource


class PolicyConstraint(StrEnum):
    """Factor 25. Enforced in the environment, never merely stated in the prompt."""

    NO_NEW_DEPENDENCIES = "no_new_dependencies"
    PROTECTED_PATH = "protected_path"


class TaskPin(FrozenModel):
    """One real task instance: a repository at a commit, an issue, and measured properties.

    Family A levels are selected for, not set, so every pool-realised factor of the full
    envelope is recorded here at build time. ``repo`` is the resource statistics cluster on.
    """

    key: str = Field(description="Instance id, e.g. the SWE-bench instance_id; used for canaries")
    repo: str = Field(description="Repository name; the bootstrap cluster")
    url: str
    commit: str
    issue: str = Field(description="Issue text shown to the agent")
    test_command: str
    fail_to_pass: tuple[str, ...] = Field(min_length=1)
    pass_to_pass: tuple[str, ...] = ()
    properties: dict[str, str] = Field(
        description="Full-envelope level of every measured pool factor, e.g. test_runner: standard"
    )
    image: str | None = Field(default=None, description="Pre-built image digest, if cached")
    test_patch: str | None = None
    image_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verification_receipt: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    workdir: str | None = None
    python_env: Literal["image", "conda_testbed"] = "image"
    source_notice: SourceNotice | None = None
    gold_patch: str | None = Field(
        default=None, description="Merged-PR diff, for construction proofs"
    )
    public_benchmark: str | None = Field(
        default=None,
        description="Public benchmark this instance comes from, for contamination notes",
    )
    protected_paths: tuple[str, ...] = Field(
        default=("tests/",), description="Paths a protected-path policy forbids touching"
    )


class SweTaskSpec(FrozenModel):
    """The task as the agent experiences it. Never contains the oracle."""

    pin: TaskPin
    perturbation: ProgramSource | None = None
    perturbation_clauses: tuple[str, ...] = ()
    clause_cell: Cell = Field(default_factory=lambda: Cell(levels={}))
    constraints: tuple[PolicyConstraint, ...] = ()
    tool_set: Literal["full", "bash_only"] = "full"
    step_budget: int = Field(default=60, ge=1)
    observation_limit: int = Field(default=100_000, ge=1, description="Characters per tool result")
    prior_turns: tuple[Message, ...] = Field(
        default=(), description="Context injected before the task (context length, wrong assertion)"
    )
    self_report_required: bool = False
    interrupted: bool = False
    handoff: bool = False
    canary: str = Field(
        description="Unique marker so leakage of this task into training is detectable"
    )


class SweOracle(FrozenModel):
    """Ground truth for the dual oracle. Hidden from the agent."""

    test_command: str
    fail_to_pass: tuple[str, ...] = Field(description="Tests that must go from failing to passing")
    pass_to_pass: tuple[str, ...] = Field(default=(), description="Tests that must keep passing")
    protected_paths: tuple[str, ...] = Field(
        default=(), description="Paths that must be untouched when a protected-path policy holds"
    )
    forbid_new_dependencies: bool = False
    expected_packages: dict[str, str] = Field(
        default_factory=dict, description="package -> version the final state must show"
    )
    gold_patch: str | None = Field(
        default=None, description="Present when the task came from a real PR"
    )
    canary: str
