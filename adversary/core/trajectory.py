"""What a target did in an environment, and the budget it did it under."""

from typing import Any, Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.model import Message, Usage


class Budget(FrozenModel):
    """Resource limits for one episode."""

    max_steps: int = Field(default=50, ge=1, description="Model calls before forced stop")
    max_seconds: float = Field(default=1800.0, gt=0, description="Wall-clock limit")
    max_tokens: int | None = Field(default=None, ge=1, description="Total token cap, if any")


class Trajectory(FrozenModel):
    """The full record of one episode from the target's side.

    ``final_state`` is an environment snapshot captured for the verifier so verification
    can be re-run offline after the environment is gone. ``claimed_success`` is the
    target's own self-report, extracted by the environment; comparing it with the verdict
    is the honesty measurement. ``realised`` says whether every perturbation the instance
    scheduled was actually applied during the run; an episode where it was not does not
    measure its cell and is excluded from cell statistics while still being reported.
    """

    instance_id: str
    model_id: str
    messages: tuple[Message, ...] = Field(description="Every turn, including tool results")
    final_state: Any = Field(default=None, description="Environment snapshot for the verifier")
    claimed_success: bool | None = Field(
        default=None, description="The target's self-report, if the environment elicits one"
    )
    realised: bool = Field(
        default=True,
        description="Every scheduled perturbation was applied; False means the cell was not met",
    )
    usage: Usage = Field(default_factory=Usage)
    steps: int = Field(default=0, ge=0, description="Model calls made")
    truncated: bool = Field(default=False, description="Whether the budget stopped the episode")
    stop_reason: Literal["submitted", "model_stopped", "step_budget", "time_budget"] | None = None
    error: str | None = Field(default=None, description="Infrastructure error, if the run broke")
