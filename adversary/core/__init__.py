"""Core primitives shared by every layer: envelope, instances, verdicts, episodes, models."""

from adversary.core.config import FrozenModel, StrictModel
from adversary.core.episode import Episode, Stage, Unreached
from adversary.core.factors import Atom, Cell, Factor, FactorSpace, Grounding
from adversary.core.generator import Generator
from adversary.core.instance import Instance, Provenance
from adversary.core.manifest import Manifest, build_manifest, verify_manifest
from adversary.core.model import (
    Completion,
    CompletionRequest,
    LanguageModel,
    LicenseClass,
    LicenseError,
    Message,
    ModelInfo,
    Role,
    ToolCall,
    Usage,
)
from adversary.core.planted import PlantedMode
from adversary.core.registry import Registry
from adversary.core.trajectory import Budget, Trajectory
from adversary.core.verify import Verdict, Verifier

__all__ = [
    "Atom",
    "Budget",
    "Cell",
    "Completion",
    "CompletionRequest",
    "Episode",
    "Factor",
    "FactorSpace",
    "FrozenModel",
    "Generator",
    "Grounding",
    "Instance",
    "LanguageModel",
    "LicenseClass",
    "LicenseError",
    "Manifest",
    "Message",
    "PlantedMode",
    "ModelInfo",
    "Provenance",
    "Registry",
    "Role",
    "Stage",
    "StrictModel",
    "ToolCall",
    "Trajectory",
    "Unreached",
    "Usage",
    "Verdict",
    "Verifier",
    "build_manifest",
    "verify_manifest",
]
