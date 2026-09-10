"""The critic: rejects drafts before anything counts.

Two kinds. :class:`StaticCritic` is code: the programs load, the generator is deterministic,
the oracle does not leak into what the target sees, the verifier imports no model. An LLM
critic may triage ambiguity but can only reject; it cannot admit. :class:`CriticChain` runs
several and admits only if all do.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell, FactorSpace
from adversary.core.instance import Instance
from adversary.core.model import CompletionRequest, LanguageModel, Message
from adversary.core.registry import Registry
from adversary.core.util import canonical_json
from adversary.probe.executor import ConfinedPrograms, ProgramExecutor
from adversary.search.draft import ProbeDraft


class Reason(StrEnum):
    """Why a draft was rejected."""

    MALFORMED = "malformed"
    NONDETERMINISM = "nondeterminism"
    LABEL_LEAKAGE = "label_leakage"
    AMBIGUITY = "ambiguity"
    IMPOSSIBILITY = "impossibility"


class Objection(FrozenModel):
    """One reason with detail."""

    reason: Reason
    detail: str


class Critique(FrozenModel):
    """Verdict on a draft."""

    accepted: bool
    objections: tuple[Objection, ...] = ()
    critic: str = Field(description="Which critic produced this")


class Critic(ABC):
    """Audits a draft."""

    @abstractmethod
    def critique(self, draft: ProbeDraft) -> Critique:
        """Accept or reject with objections."""


CRITICS: Registry[type[Critic]] = Registry("critic")


@CRITICS.register("static")
class StaticCritic(Critic):
    """Code checks. The only critic whose acceptance counts.

    With a factor space, pair cells are completed with the pinned levels before the generator
    is exercised, exactly as the falsifier will complete them. Factors or levels the envelope
    does not declare are permitted: inventing them is the search layer's job, and the report
    lists such probes as outside the swept envelope.
    """

    def __init__(
        self,
        space: FactorSpace | None = None,
        determinism_draws: int = 3,
        generator_config: dict[str, Any] | None = None,
        executor: ProgramExecutor | None = None,
    ) -> None:
        if determinism_draws < 1:
            raise ValueError("determinism_draws must be positive")
        self.executor = executor
        self.generator_config = deepcopy(generator_config or {})
        self.space = space
        self.determinism_draws = determinism_draws

    def critique(self, draft: ProbeDraft) -> Critique:
        # Only explicitly trusted callers may opt into host execution for v2 source.
        executor = self.executor or (
            ConfinedPrograms()
            if draft.perturbation is not None or draft.authored_by
            else ProgramExecutor()
        )
        try:
            # model_copy can bypass validators; recheck the complete input before execution.
            draft = ProbeDraft.model_validate(draft.model_dump(mode="python"))
        except (TypeError, ValueError) as exc:
            return Critique(
                accepted=False,
                critic="static",
                objections=(Objection(reason=Reason.MALFORMED, detail=str(exc)),),
            )
        objections: list[Objection] = []
        for program in (
            draft.generator,
            draft.verifier,
            *([draft.perturbation] if draft.perturbation else []),
        ):
            for problem in program.check():
                objections.append(
                    Objection(reason=Reason.MALFORMED, detail=f"{program.kind}: {problem}")
                )
        if objections:
            return Critique(accepted=False, objections=tuple(objections), critic="static")
        try:
            executor.inspect(draft.generator, draft.pair.treatment)
            executor.inspect(draft.verifier, draft.pair.treatment)
            if draft.perturbation is not None:
                for cell in (draft.pair.control, draft.pair.treatment):
                    intervention = executor.inspect(draft.perturbation, cell)
                    if (
                        intervention["channel"] != draft.channel
                        or tuple(intervention["clauses"]) != draft.clauses
                    ):
                        raise ValueError("program channel or clauses differ from the declaration")
                if draft.seed is None:
                    raise ValueError("perturbation draft has no mined seed")
                if not self.generator_config:
                    raise ValueError("grounded draft requires trusted generator inputs")
        except Exception as exc:  # noqa: BLE001 - a draft that raises is a rejected draft
            return Critique(
                accepted=False,
                objections=(Objection(reason=Reason.MALFORMED, detail=str(exc)),),
                critic="static",
            )
        for cell in (draft.pair.control, draft.pair.treatment):
            result = self._check_arm(draft, cell, executor)
            objections.extend(result.objections)
        return Critique(accepted=not objections, objections=tuple(objections), critic="static")

    def _check_arm(self, draft: ProbeDraft, cell: Cell, executor: ProgramExecutor) -> Critique:
        objections: list[Objection] = []
        try:
            cell = self.space.complete(cell) if self.space else cell
            config = (
                _jsonable_tree(self.generator_config)
                if executor.confined
                else self.generator_config
            )
            first = executor.generate(
                draft.generator, cell, 0, deepcopy(config), self.determinism_draws
            )
            second = executor.generate(
                draft.generator, cell, 0, deepcopy(config), self.determinism_draws
            )
        except Exception as exc:  # noqa: BLE001 - any generator crash is a malformed draft
            return Critique(
                accepted=False,
                objections=(
                    Objection(reason=Reason.MALFORMED, detail=f"generator raised {exc!r}"),
                ),
                critic="static",
            )
        try:
            if len(first) != self.determinism_draws or len(second) != self.determinism_draws:
                raise ValueError("generator returned the wrong draw count")
            if any(not isinstance(i, Instance) for i in (*first, *second)):
                raise ValueError("generator must emit Instance objects")
            identical = [_stable_instance(i) for i in first] == [
                _stable_instance(i) for i in second
            ]
        except Exception as exc:  # noqa: BLE001 - malformed generated payloads must be rejected
            return Critique(
                accepted=False,
                critic="static",
                objections=(
                    Objection(
                        reason=Reason.MALFORMED, detail=f"payload is not serialisable: {exc}"
                    ),
                ),
            )
        if not identical:
            objections.append(
                Objection(
                    reason=Reason.NONDETERMINISM, detail="same seed produced different instances"
                )
            )
        for instance in (*first, *second):
            if draft.perturbation is not None:
                for key in ("spec", "oracle", "resource"):
                    if _jsonable(getattr(instance, key)) != _jsonable(
                        self.generator_config.get(key)
                    ):
                        objections.append(
                            Objection(
                                reason=Reason.MALFORMED, detail=f"generator changed trusted {key}"
                            )
                        )
                if instance.provenance.source_license != self.generator_config.get(
                    "source_license"
                ):
                    objections.append(
                        Objection(
                            reason=Reason.MALFORMED, detail="generator changed source licence"
                        )
                    )
            if not instance.cell.covers(cell):
                objections.append(
                    Objection(
                        reason=Reason.MALFORMED, detail="instance does not realise the draft cell"
                    )
                )
                break
            try:
                oracle_text = canonical_json(_jsonable(instance.oracle))
                spec_text = canonical_json(_jsonable(instance.spec))
            except (TypeError, ValueError) as exc:
                objections.append(
                    Objection(
                        reason=Reason.MALFORMED,
                        detail=f"instance payload is not JSON-serialisable: {exc}",
                    )
                )
                break
            if len(oracle_text) > 4 and oracle_text in spec_text:
                objections.append(
                    Objection(
                        reason=Reason.LABEL_LEAKAGE, detail="oracle appears verbatim in the spec"
                    )
                )
                break
        return Critique(accepted=not objections, objections=tuple(objections), critic="static")


class ConfinedStaticCritic(StaticCritic):
    """Production structural gate for model-authored programs."""

    def __init__(self, **config: Any) -> None:
        super().__init__(executor=ConfinedPrograms(), **config)


def _stable_instance(instance: Any) -> str:
    payload = instance.model_dump(mode="python")
    payload["provenance"].pop("created_at", None)
    return canonical_json(_jsonable_tree(payload))


def _jsonable_tree(value: Any) -> Any:
    value = _jsonable(value)
    if isinstance(value, dict):
        return {k: _jsonable_tree(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable_tree(v) for v in value]
    return value


def _jsonable(value: object) -> object:
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else value


@CRITICS.register("llm")
class LLMCritic(Critic):
    """A model triages ambiguity and impossibility. It can reject, never admit on its own."""

    def __init__(self, model: LanguageModel, max_tokens: int = 512) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def critique(self, draft: ProbeDraft) -> Critique:
        prompt = (
            "Audit this probe hypothesis and its generator for ambiguity (multiple defensible "
            "answers) "
            "and impossibility (no correct answer exists). Reply 'OK' or one line starting with "
            "'AMBIGUOUS:' or 'IMPOSSIBLE:'.\n\n"
            f"Hypothesis: {draft.hypothesis}\nCell: {draft.cell.label()}\n\n"
            f"{draft.generator.source[:6000]}"
        )
        reply = self.model.complete(
            CompletionRequest(
                messages=(Message(role="user", content=prompt),), max_tokens=self.max_tokens
            )
        ).message.content.strip()
        if reply.upper().startswith("AMBIGUOUS"):
            return Critique(
                accepted=False,
                objections=(Objection(reason=Reason.AMBIGUITY, detail=reply),),
                critic="llm",
            )
        if reply.upper().startswith("IMPOSSIBLE"):
            return Critique(
                accepted=False,
                objections=(Objection(reason=Reason.IMPOSSIBILITY, detail=reply),),
                critic="llm",
            )
        if reply.upper() != "OK":
            return Critique(
                accepted=False,
                critic="llm",
                objections=(
                    Objection(
                        reason=Reason.MALFORMED, detail="critic reply was not an explicit decision"
                    ),
                ),
            )
        return Critique(accepted=True, critic="llm")


class CriticChain(Critic):
    """All critics must accept; objections are pooled. A static critic must be present."""

    def __init__(self, critics: Sequence[Critic]) -> None:
        if not any(isinstance(c, StaticCritic) for c in critics):
            raise ValueError(
                "a CriticChain must include a StaticCritic; judges triage, code decides"
            )
        self.critics = tuple(critics)

    def critique(self, draft: ProbeDraft) -> Critique:
        results = []
        ordered = sorted(self.critics, key=lambda c: not isinstance(c, StaticCritic))
        for critic in ordered:
            result = critic.critique(draft)
            results.append(result)
            if not result.accepted:
                break
        return Critique(
            accepted=all(r.accepted for r in results),
            objections=tuple(o for r in results for o in r.objections),
            critic="+".join(r.critic for r in results),
        )
