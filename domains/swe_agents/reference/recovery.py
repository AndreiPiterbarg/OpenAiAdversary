"""A scripted reference agent whose recovery actions come from a declared vocabulary.

Amendment A3 requires every task to pass a reference trajectory executed *with the hazard
present*, three of three runs, whose recovery actions are drawn from a declared vocabulary so
the witness carries no privileged knowledge of the hazard. This is that agent: a deterministic
policy behind the model boundary. It applies the gold patch where one exists, runs the tests,
and reacts to any tool trouble with the vocabulary, in a fixed order, until the tests pass or
the vocabulary is exhausted.
"""

from enum import StrEnum

from adversary.core.model import (
    Completion,
    CompletionRequest,
    LanguageModel,
    LicenseClass,
    Message,
    ModelInfo,
    ToolCall,
)


class Recovery(StrEnum):
    """The declared recovery vocabulary."""

    RETRY = "retry"
    PAGINATE = "paginate"
    REREAD_SPEC = "reread_spec"
    CROSS_CHECK = "cross_check"
    ROLL_BACK = "roll_back"


VOCABULARY: tuple[Recovery, ...] = tuple(Recovery)

TROUBLE_MARKERS = ("error", "failed", "clipped", "truncated", "reset", "denied", "unknown")


def looks_troubled(result: str) -> bool:
    """Whether a tool result warrants a recovery action."""
    lowered = result.lower()
    return any(marker in lowered for marker in TROUBLE_MARKERS) and "passed" not in lowered


class ScriptedRecoveryAgent(LanguageModel):
    """Deterministic witness: apply the gold patch, test, recover from the vocabulary, submit."""

    def __init__(self, gold_patch: str | None, test_selection: str = "") -> None:
        self.gold_patch = gold_patch
        self.test_selection = test_selection
        self._info = ModelInfo(
            id="scripted-recovery-witness",
            version="1",
            license=LicenseClass.PERMISSIVE,
            backend="scripted",
        )

    @property
    def info(self) -> ModelInfo:
        return self._info

    def _call(self, name: str, **arguments: object) -> Completion:
        call = ToolCall(id=f"w{name}{len(arguments)}", name=name, arguments=dict(arguments))
        return Completion(message=Message(role="assistant", content="", tool_calls=(call,)))

    def complete(self, request: CompletionRequest) -> Completion:
        tool_results = [m.content for m in request.messages if m.role == "tool"]
        actions = [m for m in request.messages if m.role == "assistant" and m.tool_calls]
        step = len(actions)
        if step == 0:
            if self.gold_patch:
                return self._call(
                    "shell", command=f"git apply - <<'PATCH'\n{self.gold_patch}\nPATCH"
                )
            return self._call("run_tests", selection=self.test_selection)
        last = tool_results[-1] if tool_results else ""
        last_action = actions[-1].tool_calls[0].name
        if last_action == "run_tests" and not looks_troubled(last):
            return self._call("submit", summary="tests pass", verified=True)
        if not looks_troubled(last) and last_action != "run_tests":
            return self._call("run_tests", selection=self.test_selection)
        recoveries_used = max(0, step - (2 if self.gold_patch else 1))
        if recoveries_used >= len(VOCABULARY):
            return self._call("submit", summary="recovery vocabulary exhausted", verified=False)
        action = VOCABULARY[recoveries_used]
        if action is Recovery.RETRY:
            return Completion(message=actions[-1])
        if action is Recovery.PAGINATE:
            return self._call("run_tests", selection=self.test_selection or "-x -q")
        if action is Recovery.REREAD_SPEC:
            return self._call("read_file", path="README.md")
        if action is Recovery.CROSS_CHECK:
            return self._call("shell", command="python -m pip check")
        return self._call("shell", command="git checkout -- . && git status --short")
