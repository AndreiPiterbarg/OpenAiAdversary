"""A deterministic fake model for tests and dry runs.

It lets the harness, the statistics and the falsification loop be exercised end to end
without loading weights. A policy function maps a request to an assistant message.
"""

from collections.abc import Callable

from adversary.core.model import (
    Completion,
    CompletionRequest,
    LanguageModel,
    LicenseClass,
    Message,
    ModelInfo,
)
from adversary.execution.backends import MODELS

Policy = Callable[[CompletionRequest], Message]


@MODELS.register("scripted")
class ScriptedModel(LanguageModel):
    """Answers with whatever ``policy`` returns; defaults to echoing the last user turn."""

    def __init__(
        self,
        policy: Policy | None = None,
        model_id: str = "scripted",
        version: str = "0",
        license: LicenseClass = LicenseClass.PERMISSIVE,
    ) -> None:
        self._policy = policy or self._echo
        self._info = ModelInfo(id=model_id, version=version, license=license, backend="scripted")
        self.calls = 0

    @property
    def info(self) -> ModelInfo:
        return self._info

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls += 1
        return Completion(message=self._policy(request))

    @staticmethod
    def _echo(request: CompletionRequest) -> Message:
        last = request.messages[-1].content if request.messages else ""
        return Message(role="assistant", content=last)
