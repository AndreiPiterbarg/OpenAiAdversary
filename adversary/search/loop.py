"""Layer 2 orchestration: propose, critique, referee, falsify, archive, mutate.

One iteration is one hypothesis. The loop keeps counts of where drafts died so the report can
say how much of the search budget the critic, the referee and the minimal pair each consumed.
"""

import random
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel, StrictModel
from adversary.core.instance import Instance
from adversary.core.model import LanguageModel
from adversary.core.seeds import SeedRange
from adversary.execution.store import EpisodeStore
from adversary.probe.kill import KillRecord
from adversary.probe.library import ProbeLibrary
from adversary.probe.probe import Probe, ProbeStatus
from adversary.search.archive import Archive, CappedRelease, Elite, EpochManifest
from adversary.search.context import SearchContext
from adversary.search.critic import Critic, LLMCritic
from adversary.search.falsify import Falsifier
from adversary.search.mutator import Mutator
from adversary.search.proposer import ProposalError, Proposer
from adversary.search.referee import Referee


class SearchConfig(StrictModel):
    """Budget and knobs for one search run."""

    iterations: int = Field(default=20, ge=1, description="Hypotheses to attempt")
    referee_sample: int = Field(default=5, ge=1, description="Instances certified per draft")
    seeds: SeedRange = Field(
        default=SeedRange(start=1_000_000, stop=2_000_000),
        description="Seeds for minimal pairs; disjoint from the sweep and from repair",
    )
    mutate_probability: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Chance to mutate an elite instead of proposing"
    )
    sentinel: bool = Field(
        default=False,
        description=(
            "Amendment A9: run the proposer with archive, hot-cell and transcript conditioning "
            "removed and no mutation. Only a sentinel stream may feed unseen-species estimates."
        ),
    )
    rng_seed: int = 0


class SearchReport(FrozenModel):
    """Where the budget went and what survived."""

    proposed: int
    malformed: int = Field(description="Proposer output that did not parse")
    rejected_by_critic: int
    rejected_by_referee: int
    killed: int
    survived: int
    elites: tuple[Elite, ...]
    kills: tuple[KillRecord, ...]
    probes: tuple[Probe, ...] = Field(description="Every probe that reached the falsifier")
    lineage: tuple[tuple[str, str | None], ...] = Field(
        default=(), description="(probe id, parent id) for every probe that reached the falsifier"
    )
    source: Literal["directed", "sentinel"] = "directed"


class SearchLoop:
    """Runs the hypothesis loop against one target."""

    def __init__(
        self,
        proposer: Proposer,
        critic: Critic,
        referee: Referee,
        falsifier: Falsifier,
        archive: Archive,
        mutator: Mutator | None = None,
        library: ProbeLibrary | None = None,
    ) -> None:
        if isinstance(critic, LLMCritic):
            raise ValueError("an LLM critic must be inside a chain with a static gate")
        self.proposer = proposer
        self.critic = critic
        self.referee = referee
        self.falsifier = falsifier
        self.archive = archive
        self.mutator = mutator
        self.library = library

    def run(
        self, context: SearchContext, model: LanguageModel, config: SearchConfig
    ) -> SearchReport:
        """Execute ``config.iterations`` hypotheses."""
        if context.mined_seed is not None or context.space is None:
            raise RuntimeError(
                "v2 search refused: confined execution, build and gold-patch admission "
                "are not wired; structural critique alone cannot authorize episodes"
            )
        rng = random.Random(config.rng_seed)
        counts = {
            "proposed": 0,
            "malformed": 0,
            "critic": 0,
            "referee": 0,
            "killed": 0,
            "survived": 0,
        }
        kills: list[KillRecord] = []
        probes: list[Probe] = []
        fingerprint = context.space.fingerprint()

        live_context = context.stripped() if config.sentinel else context.model_copy(deep=True)
        frozen_parents = tuple(self.archive.probe(e.probe_id) for e in self.archive.elites())
        for iteration in range(config.iterations):
            counts["proposed"] += 1
            try:
                may_mutate = self.mutator and frozen_parents and not config.sentinel
                if may_mutate and rng.random() < config.mutate_probability:
                    parent = rng.choice(frozen_parents)
                    draft = self.mutator.mutate(parent, live_context)
                else:
                    draft = self.proposer.propose(live_context)
            except ProposalError:
                counts["malformed"] += 1
                continue

            if draft.perturbation is not None:
                raise RuntimeError(
                    "v2 search refused: confined perturbation execution and admission are unwired"
                )
            critique = self.critic.critique(draft)
            if not critique.accepted:
                counts["critic"] += 1
                continue

            probe = draft.to_probe(fingerprint)
            seed = config.seeds.at(iteration)
            sample = probe.generator.load()(
                self.falsifier.space.complete(probe.pair.treatment), seed=seed
            ).generate_batch(config.referee_sample)
            if not self.referee.admit(sample).admitted:
                counts["referee"] += 1
                continue
            probe = probe.with_(status=ProbeStatus.ADMITTED)

            outcome = self.falsifier.test(probe, model, seed=seed)
            probe = probe.with_kill(outcome.record)
            kills.append(outcome.record)
            if outcome.survived:
                counts["survived"] += 1
                probe = probe.with_(status=ProbeStatus.MEASURED)
                self.archive.offer(probe, score=outcome.record.measured.effect)
                if self.library is not None:
                    self.library.add(probe)
            else:
                counts["killed"] += 1
            probes.append(probe)

        return SearchReport(
            proposed=counts["proposed"],
            malformed=counts["malformed"],
            rejected_by_critic=counts["critic"],
            rejected_by_referee=counts["referee"],
            killed=counts["killed"],
            survived=counts["survived"],
            elites=tuple(self.archive.elites()),
            kills=tuple(kills),
            probes=tuple(probes),
            lineage=tuple((p.id, p.provenance.parent_id) for p in probes),
            source="sentinel" if config.sentinel else "directed",
        )


def run_frozen_epoch(
    epoch: "EpochManifest",
    context: SearchContext,
    candidates: "Sequence[Instance]",
    score: "Callable[[Instance], float]",
    store: "EpisodeStore",
    release_seed: int,
) -> "CappedRelease":
    """Score a complete admitted instance batch without updating proposal context.

    Admission and generation precede this function. This is the registered research boundary,
    not a claim about later program outputs or downstream selection.
    """
    from adversary.core.util import sha256_json
    from adversary.search.archive import capped_release

    if sha256_json(context.model_dump(mode="json")) != epoch.context_digest:
        raise ValueError("proposal context differs from frozen epoch")
    if len(candidates) != epoch.m:
        raise ValueError("fixed admitted instance batch is incomplete")
    payloads = [candidate.model_dump_json() for candidate in candidates]
    digests = [sha256_json(candidate.model_dump(mode="json")) for candidate in candidates]
    scores = [score(Instance.model_validate_json(payload)) for payload in payloads]
    if sha256_json(context.model_dump(mode="json")) != epoch.context_digest:
        raise ValueError("context changed within the frozen batch")
    release = capped_release(epoch, digests, scores, release_seed)
    store.record_epoch(epoch.model_dump(mode="json"), release.model_dump(mode="json"))
    return release
