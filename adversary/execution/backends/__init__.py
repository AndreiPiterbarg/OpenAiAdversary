"""Model backends: every way a :class:`~adversary.core.model.LanguageModel` can be called.

Backends register under a name so run configs can name them. ``discover()`` is invoked by
:func:`build_model`, so a backend module only needs to exist under this package to be usable.
"""

from typing import Any

from adversary.core.model import LanguageModel
from adversary.core.registry import Registry

MODELS: Registry[type[LanguageModel]] = Registry("model backend")


def build_model(backend: str, **config: Any) -> LanguageModel:
    """Instantiate a registered backend by name with its config keywords."""
    MODELS.discover(__name__)
    return MODELS.get(backend)(**config)


__all__ = ["MODELS", "build_model"]
