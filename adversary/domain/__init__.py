"""The domain plugin contract and registry."""

from adversary.domain.contract import (
    CorpusSource,
    Domain,
    Environment,
    EnvironmentBuilder,
    RealCorpus,
    Reference,
    SolvabilityCertificate,
)
from adversary.domain.registry import DOMAINS, load_domain

__all__ = [
    "DOMAINS",
    "CorpusSource",
    "Domain",
    "Environment",
    "EnvironmentBuilder",
    "RealCorpus",
    "Reference",
    "SolvabilityCertificate",
    "load_domain",
]
