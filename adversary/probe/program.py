"""Executable program sources: the ``gen`` and ``check`` halves of a probe.

A probe ships as code, so its generator and verifier are stored as source text with an
entrypoint class name and a content hash. :meth:`ProgramSource.load` executes the source in a
fresh module and returns the class, after :meth:`ProgramSource.check` has rejected anything
malformed. Verifier programs may not import the model boundary or anything that reaches the
network: the final arbiter is code, and this is where that rule becomes a check rather than a
sentence in a document.

Sandboxing of untrusted generated code is the execution layer's job (run it where the
environments run). This module is a structural gate, not a security boundary.
"""

import ast
import random
import sys
import types
from enum import StrEnum

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.generator import Generator
from adversary.core.instance import Instance, Provenance
from adversary.core.trajectory import Trajectory
from adversary.core.util import sha256_text
from adversary.core.verify import Verdict, Verifier
from adversary.domain.channel import Channel
from adversary.domain.perturbation import Perturbation


class ProgramKind(StrEnum):
    """Which half of the probe a program is."""

    GENERATOR = "generator"
    VERIFIER = "verifier"
    PERTURBATION = "perturbation"


FORBIDDEN_VERIFIER_MODULES = (
    "adversary.core.model",
    "adversary.execution",
    "urllib",
    "http",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "openai",
    "anthropic",
    "google",
)
"""A verifier that imports the model boundary or a network client is not code deciding."""

FORBIDDEN_VERIFIER_NAMES = ("LanguageModel", "build_model", "MODELS")

PROGRAM_NAMESPACE = (
    Generator,
    Verifier,
    Perturbation,
    Channel,
    Instance,
    Provenance,
    Cell,
    Verdict,
    Trajectory,
    random,
)
"""Bound in every program's execution namespace.

A probe must subclass ``Generator`` and construct an ``Instance``; requiring it to import
them as well would couple every shipped program to this package's layout and is the one
import that cannot resolve. E0 measured the cost of providing neither: 0 of 200 admitted.
"""


class ProgramError(ValueError):
    """The program is malformed or violates a structural rule."""


class ProgramSource(FrozenModel):
    """Source text plus the class it defines."""

    kind: ProgramKind
    source: str = Field(description="Python source defining ``entrypoint``")
    entrypoint: str = Field(description="Name of the Generator or Verifier subclass in ``source``")

    @property
    def digest(self) -> str:
        """SHA-256 of the source; the program's version."""
        return sha256_text(self.source)

    def check(self) -> list[str]:
        """Static problems with the program; empty means it may be loaded."""
        problems: list[str] = []
        try:
            tree = ast.parse(self.source)
        except SyntaxError as exc:
            return [f"syntax error: {exc.msg} (line {exc.lineno})"]
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        if self.entrypoint not in defined:
            problems.append(f"entrypoint {self.entrypoint!r} is not a class defined in the source")
        if self.kind is ProgramKind.VERIFIER:
            for node in ast.walk(tree):
                modules: list[str] = []
                names: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                    names = [alias.name for alias in node.names]
                for module in modules:
                    root = module.split(".")[0]
                    if module.startswith(FORBIDDEN_VERIFIER_MODULES) or root in (
                        FORBIDDEN_VERIFIER_MODULES
                    ):
                        problems.append(
                            f"verifier imports {module}; verifiers are code, never a model"
                        )
                for name in names:
                    if name in FORBIDDEN_VERIFIER_NAMES:
                        problems.append(
                            f"verifier imports {name}; verifiers are code, never a model"
                        )
        return problems

    def load(self) -> type:
        """Execute the source and return the entrypoint class.

        The module is registered in ``sys.modules`` under a digest-derived name so classes
        defined in it resolve their own module (pydantic forward references need this), and
        ``Generator`` and ``Verifier`` are bound in its namespace before execution. A probe is
        required to subclass them, so requiring it to import them as well would couple every
        shipped program to this package's layout; E0 measured what happens when neither is
        provided (55 of 68 parsed drafts lost).

        Raises:
            ProgramError: If :meth:`check` reports problems or the class has the wrong base.
        """
        problems = self.check()
        if problems:
            raise ProgramError("; ".join(problems))
        name = f"probe_program_{self.digest[:16]}"
        module = types.ModuleType(name)
        module.__file__ = f"<probe:{self.digest[:16]}>"
        for symbol in PROGRAM_NAMESPACE:
            setattr(module, symbol.__name__, symbol)
        sys.modules[name] = module
        try:
            exec(compile(self.source, module.__file__, "exec"), module.__dict__)  # noqa: S102
        except Exception as exc:  # noqa: BLE001 - model-written source may raise anything
            raise ProgramError(f"source raised on execution: {exc!r}") from exc
        cls = getattr(module, self.entrypoint)
        expected = {
            ProgramKind.GENERATOR: Generator,
            ProgramKind.VERIFIER: Verifier,
            ProgramKind.PERTURBATION: Perturbation,
        }[self.kind]
        if not (isinstance(cls, type) and issubclass(cls, expected)):
            raise ProgramError(f"{self.entrypoint} must subclass {expected.__name__}")
        return cls
