"""Discovery of domain plugins.

Plugins register a zero-argument factory under a name. Factories rather than instances,
because building a domain can be expensive (pulling images, indexing a corpus) and should
happen when a run asks for it, not at import time.
"""

from collections.abc import Callable

from adversary.core.registry import Registry
from adversary.domain.contract import Domain

DOMAINS: Registry[Callable[[], Domain]] = Registry("domain")


def load_domain(name: str, package: str = "domains") -> Domain:
    """Import every plugin under ``package`` and build the one called ``name``."""
    DOMAINS.discover(package)
    return DOMAINS.get(name)()
