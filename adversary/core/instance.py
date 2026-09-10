"""Generated task instances and their provenance.

An :class:`Instance` is what a generator emits and what an environment builder consumes.
``spec`` is the domain payload the plugin's environment builder consumes and ``oracle`` is
the hidden ground truth the verifier needs. The core treats both
as opaque, JSON-serialisable values. Every instance carries a :class:`Provenance` because
labs audit per-example provenance and because the same record is what lets a probe be
regenerated against a new checkpoint.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.licensing import SourceNotice
from adversary.core.model import LicenseClass
from adversary.core.util import utc_now


class Provenance(FrozenModel):
    """Where an instance came from, sufficient to regenerate it."""

    generator: str = Field(description="Generator identity: 'module:Class' or a probe id")
    generator_version: str = Field(description="Hash or version of the generator program")
    seed: int = Field(description="Seed that produced this instance")
    source_license: str | None = Field(default=None, description="Source SPDX identifier")
    source_notice: SourceNotice | None = None
    created_at: datetime = Field(default_factory=utc_now)
    authored_by: str | None = Field(
        default=None, description="Model id that wrote the generator program, if any"
    )
    author_license: LicenseClass | None = Field(
        default=None, description="Licence class of the authoring model, if any"
    )
    extra: dict[str, str] = Field(
        default_factory=dict, description="Domain-specific provenance such as image digests"
    )


class Instance(FrozenModel):
    """One generated task: domain payload, hidden oracle, the cell it realises."""

    id: str = Field(description="Content-addressed id; equal instances share an id")
    cell: Cell = Field(description="Factor levels this instance realises (full configuration)")
    seed: int = Field(description="Per-instance seed derived from the generator's stream")
    spec: Any = Field(description="Domain payload consumed by the plugin's environment builder")
    oracle: Any = Field(description="Ground truth for the verifier; never shown to the target")
    provenance: Provenance
    perturbation_config: dict[str, Any] = Field(default_factory=dict)
    resource: str | None = Field(
        default=None,
        description=(
            "Pool member this instance draws on (one code base, one document set). Statistics "
            "cluster on it so many instances from one resource are not independent evidence."
        ),
    )
    canary: str | None = Field(
        default=None,
        description="Unique marker in eval instances so leakage into training is detectable",
    )
