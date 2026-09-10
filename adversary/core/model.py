"""The single boundary behind which every language model sits.

Targets under attack, the proposer that writes probe programs, and frontier models used
for transfer checks are all :class:`LanguageModel` instances. Everything above this
boundary is indifferent to whether a model is a local ``transformers`` checkpoint, a served
engine on a GPU box, or a vendor API. Backends live in ``adversary.execution.backends``.

The boundary also carries the legal posture as data: :attr:`LanguageModel.license` says
whether a model's outputs may enter shipped artefacts. Frontier API terms prohibit using
outputs to build competing models, so those models are ``RESTRICTED`` and the repair layer
refuses their trajectories structurally rather than by policy.
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel


class LicenseClass(StrEnum):
    """Whether a model's outputs may enter shipped artefacts."""

    PERMISSIVE = "permissive"
    """Apache-2.0 / MIT class weights. Outputs may be shipped."""

    RESTRICTED = "restricted"
    """Vendor API terms forbid building competing models from outputs. Transfer checks only."""


class LicenseError(ValueError):
    """A restricted-licence model or artefact was offered where only shippable ones may go."""


class Role(StrEnum):
    """Why a model is present in a run; recorded in provenance."""

    TARGET = "target"
    PROPOSER = "proposer"
    REFERENCE = "reference"
    TRANSFER = "transfer"


class ToolCall(FrozenModel):
    """A tool invocation requested by the model."""

    id: str = Field(description="Caller-visible id used to pair the call with its result")
    name: str = Field(description="Tool name from the request's tool specs")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Parsed JSON arguments")


class Message(FrozenModel):
    """One turn of a conversation; the same shape is used inside trajectories."""

    role: str = Field(description="'system', 'user', 'assistant' or 'tool'")
    content: str = Field(default="", description="Text content")
    tool_calls: tuple[ToolCall, ...] = Field(
        default=(), description="Calls made by an assistant turn"
    )
    response_items: tuple[dict[str, Any], ...] = ()
    tool_call_id: str | None = Field(
        default=None, description="For 'tool' turns: the call answered"
    )


class CompletionRequest(FrozenModel):
    """A single call to a model, independent of backend."""

    messages: tuple[Message, ...] = Field(description="Conversation so far")
    tools: tuple[dict[str, Any], ...] = Field(
        default=(), description="JSON-schema tool specifications the model may call"
    )
    max_tokens: int = Field(default=2048, ge=1, description="Generation cap")
    temperature: float = Field(default=0.0, ge=0.0, description="Sampling temperature")
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=-1)
    chat_template_kwargs: dict[str, Any] | None = None
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    thinking_budget: int | None = Field(
        default=None, ge=0, description="Extended-thinking budget where supported; None = off"
    )
    seed: int | None = Field(
        default=None, description="Sampling seed where the backend supports it"
    )


class Usage(FrozenModel):
    """Resource accounting for one completion or one whole trajectory."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0.0)

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            wall_seconds=self.wall_seconds + other.wall_seconds,
        )


class Completion(FrozenModel):
    """What a model returned for one request."""

    message: Message = Field(description="The assistant turn produced")
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str = Field(default="stop", description="Backend's stop reason, normalised")
    raw: dict[str, Any] = Field(default_factory=dict, description="Backend payload for audit")


class ModelInfo(FrozenModel):
    """Identity and licence of a model as recorded in provenance."""

    id: str = Field(description="Stable identifier, e.g. 'Qwen/Qwen3.8-27B'")
    version: str = Field(default="", description="Checkpoint revision, adapter id or API version")
    license: LicenseClass = Field(description="Whether outputs may enter shipped artefacts")
    backend: str = Field(description="Registered backend name that serves this model")

    @property
    def shippable(self) -> bool:
        """True if outputs from this model may appear in a shipped artefact."""
        return self.license is LicenseClass.PERMISSIVE


class LanguageModel(ABC):
    """Abstract model boundary. Implement :meth:`complete` and expose :attr:`info`."""

    @property
    @abstractmethod
    def info(self) -> ModelInfo:
        """Identity, version and licence class."""

    @abstractmethod
    def complete(self, request: CompletionRequest) -> Completion:
        """Produce one assistant turn for ``request``.

        Implementations must be side-effect free with respect to the run: no caching that
        would make two episodes share a completion unless the request is identical.
        """

    @property
    def shippable(self) -> bool:
        """Convenience passthrough to :attr:`ModelInfo.shippable`."""
        return self.info.shippable


class PinField(FrozenModel):
    """One explicitly observed or unavailable component of model identity."""

    status: Literal["pinned", "unpinned"]
    value: Any = None
    reason: str = ""

    @model_validator(mode="after")
    def _explicit(self) -> "PinField":
        if self.status == "pinned" and self.value is None:
            raise ValueError("pinned field requires a value")
        if self.status == "unpinned" and (self.value is not None or not self.reason.strip()):
            raise ValueError("unpinned field requires an explicit reason and no invented value")
        return self


class TargetPin(FrozenModel):
    """All six identity fields are required, including unavailable vendor internals."""

    model: str
    checkpoint: PinField
    scaffold: PinField
    tool_set: PinField
    decoding_policy: PinField
    quantisation: PinField
    serving_kernel: PinField

    def fingerprint(self) -> str:
        from adversary.core.util import sha256_json

        return sha256_json(self.model_dump(mode="json"))
