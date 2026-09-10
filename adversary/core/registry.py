"""Generic named registry with decorator registration and package auto-discovery.

Components register themselves with a decorator
when their module is imported, and :meth:`Registry.discover` imports every module under a
package so registration happens without a hand-maintained list. One registry instance per
component kind (model backends, domain plugins, proposers) lives in the package that owns
that kind.
"""

import importlib
import logging
import pkgutil
from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)


class Registry[T]:
    """Name-to-class mapping for one kind of swappable component."""

    def __init__(self, kind: str) -> None:
        """Create an empty registry.

        Args:
            kind: Human-readable component kind used in error messages, e.g. "model backend".
        """
        self.kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        """Decorator registering a class under ``name``; duplicate names are errors."""

        def decorator(item: T) -> T:
            if name in self._items and self._items[name] is not item:
                raise KeyError(f"{self.kind} {name!r} is already registered")
            self._items[name] = item
            return item

        return decorator

    def get(self, name: str) -> T:
        """Look up a registered item or raise ``KeyError`` listing what is available."""
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(
                f"unknown {self.kind} {name!r}; registered: {sorted(self._items)}"
            ) from exc

    def names(self) -> list[str]:
        """Registered names, sorted."""
        return sorted(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __iter__(self) -> Iterator[tuple[str, T]]:
        return iter(sorted(self._items.items()))

    def discover(self, package: str) -> None:
        """Import every module under ``package`` so decorated components register.

        Args:
            package: Importable package name, e.g. ``"adversary.execution.backends"`` or
                ``"domains"``. Import failures are logged and skipped so one broken plugin
                does not hide the others.
        """
        root = importlib.import_module(package)
        path = getattr(root, "__path__", None)
        if path is None:
            return
        for info in pkgutil.walk_packages(path, prefix=f"{package}."):
            try:
                importlib.import_module(info.name)
            except ImportError as exc:  # pragma: no cover - depends on optional deps
                logger.warning("skipping %s during %s discovery: %s", info.name, self.kind, exc)
