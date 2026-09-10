"""Explicit resource contract shared by the local controller and model bridge."""

from pydantic import BaseModel, ConfigDict, Field


class EpisodeBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)

    max_steps: int = Field(default=100, ge=1)
    max_seconds: float = Field(default=600.0, gt=0)
    max_output_tokens: int = Field(default=1024, ge=1, le=1024)

    @property
    def output_request_cap(self) -> int:
        return self.max_steps * self.max_output_tokens
