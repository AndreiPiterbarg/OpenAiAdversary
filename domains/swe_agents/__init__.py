"""Software engineering tasks with explicit runtime, pin-pool and corpus inputs."""

from adversary.domain.contract import Domain, RealCorpus
from adversary.domain.registry import DOMAINS
from domains.swe_agents.environment.builder import SweEnvironmentBuilder
from domains.swe_agents.reference.solver import SweReference


@DOMAINS.register("swe_agents")
def make_domain() -> Domain:
    """Refuse unconfigured construction instead of loading retired envelope files."""
    raise ValueError("configure a builder and corpus, then call make_domain_for")


@DOMAINS.register("swe_agents_pilot")
def make_pilot_domain() -> Domain:
    """The old pilot envelope is retired; construction must name explicit inputs."""
    raise ValueError("pilot envelope retired; configure explicit task inputs")


def make_domain_for(
    builder: SweEnvironmentBuilder, corpus: RealCorpus, name: str = "swe_agents"
) -> Domain:
    """Assemble the plugin using caller-supplied, independently validated inputs."""
    return Domain(name=name, environment=builder, reference=SweReference(builder), corpus=corpus)


__all__ = ["make_domain", "make_domain_for", "make_pilot_domain"]
