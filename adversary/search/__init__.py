"""Layer 2: the hypothesis-driven, program-writing adversary."""

from adversary.search.archive import (
    Archive,
    BehaviourDescriptor,
    Elite,
    FailureSignatureDescriptor,
    Placement,
    measured_signature,
)
from adversary.search.context import EliteSummary, SearchContext
from adversary.search.critic import (
    CRITICS,
    Critic,
    CriticChain,
    Critique,
    LLMCritic,
    Objection,
    Reason,
    StaticCritic,
)
from adversary.search.draft import ProbeDraft
from adversary.search.falsify import FalsificationOutcome, Falsifier, Reproduction
from adversary.search.loop import SearchConfig, SearchLoop, SearchReport
from adversary.search.mutator import MUTATORS, LLMMutator, Mutator
from adversary.search.proposer import PROPOSERS, LLMProposer, ProposalError, Proposer, parse_draft
from adversary.search.referee import Referee, RefereeReport

__all__ = [
    "CRITICS",
    "MUTATORS",
    "PROPOSERS",
    "Archive",
    "BehaviourDescriptor",
    "Critic",
    "CriticChain",
    "Critique",
    "Elite",
    "EliteSummary",
    "FalsificationOutcome",
    "Falsifier",
    "FailureSignatureDescriptor",
    "LLMCritic",
    "LLMMutator",
    "LLMProposer",
    "Mutator",
    "Objection",
    "Placement",
    "ProbeDraft",
    "ProposalError",
    "Proposer",
    "Reason",
    "Referee",
    "RefereeReport",
    "Reproduction",
    "SearchConfig",
    "SearchContext",
    "SearchLoop",
    "SearchReport",
    "StaticCritic",
    "measured_signature",
    "parse_draft",
]
