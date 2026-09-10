"""Pydantic base classes shared by every configuration and artefact in the core.

Two bases, chosen by mutability:

* :class:`StrictModel` for configuration. Unknown fields are errors and assignments are
  re-validated.
* :class:`FrozenModel` for artefacts that are hashed, stored or shipped. Field reassignment
  is disabled; mutable values held inside fields are not recursively frozen.

Both drop ``functools.cached_property`` values when copied: pydantic's ``model_copy`` carries
the instance dictionary into the copy, and a cache computed for the original would otherwise
answer for a copy with different fields.
"""

from functools import cached_property
from typing import Any

from pydantic import BaseModel, ConfigDict


def _cached_property_names(cls: type) -> list[str]:
    return [
        name
        for klass in cls.__mro__
        for name, value in vars(klass).items()
        if isinstance(value, cached_property)
    ]


class _CacheSafeCopy(BaseModel):
    """Mixin: ``model_copy`` never carries cached properties into the copy."""

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
        copied = super().model_copy(update=update, deep=deep)
        for name in _cached_property_names(type(self)):
            copied.__dict__.pop(name, None)
        return copied


class StrictModel(_CacheSafeCopy):
    """Configuration base: unknown fields are rejected, assignments are validated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FrozenModel(_CacheSafeCopy):
    """Artefact base: immutable once constructed, unknown fields rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)
