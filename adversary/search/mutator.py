"""Mutation of probes that already work: FunSearch-style program variation."""

from abc import ABC, abstractmethod

from adversary.core.model import CompletionRequest, LanguageModel, Message
from adversary.core.registry import Registry
from adversary.probe.probe import Probe
from adversary.search.context import SearchContext
from adversary.search.draft import ProbeDraft
from adversary.search.proposer import DRAFT_SCHEMA, ProposalError, parse_draft, render_context


class Mutator(ABC):
    """Produces a draft derived from an existing probe."""

    @abstractmethod
    def mutate(self, probe: Probe, context: SearchContext) -> ProbeDraft:
        """Vary ``probe`` into a new draft with ``parent_id`` set."""


MUTATORS: Registry[type[Mutator]] = Registry("mutator")


@MUTATORS.register("llm")
class LLMMutator(Mutator):
    """A shippable model rewrites the programs to move the probe to a neighbouring region."""

    def __init__(self, model: LanguageModel, max_tokens: int = 4096) -> None:
        if not model.shippable:
            raise ValueError(
                f"mutator model {model.info.id} is restricted; its programs could not ship"
            )
        self.model = model
        self.max_tokens = max_tokens
        self.seed = 0

    def mutate(self, probe: Probe, context: SearchContext) -> ProbeDraft:
        if context.mined_seed is None:
            raise ProposalError("schema v2 mutation requires a mined seed")
        if probe.perturbation is None:
            raise ProposalError("schema v2 mutation requires a three-program parent")
        prompt = "\n\n".join(
            (
                "Mutate the probe below into a new one that targets an empty archive niche or a "
                "higher interaction order. Keep what made it fail the target; change one thing "
                "deliberately.",
                render_context(context),
                f"Parent hypothesis: {probe.hypothesis}\nParent cell: {probe.cell.label()}",
                f"Parent generator:\n{probe.generator.source}",
                f"Parent verifier:\n{probe.verifier.source}",
                f"Parent perturbation:\n{probe.perturbation.source}",
                DRAFT_SCHEMA,
            )
        )
        completion = self.model.complete(
            CompletionRequest(
                messages=(Message(role="user", content=prompt),),
                max_tokens=self.max_tokens,
                temperature=1.0,
                top_p=0.95,
                top_k=20,
                chat_template_kwargs={"enable_thinking": False},
                seed=self.seed,
            )
        )
        self.seed += 1
        draft = parse_draft(completion.message.content, self.model.info, parent_id=probe.id)
        if draft.seed != context.mined_seed:
            raise ProposalError("mutation changed the supplied mined seed")
        return draft
