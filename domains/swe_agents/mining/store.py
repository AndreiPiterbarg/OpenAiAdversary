"""Load the frozen history harvest, preserving every original grounding field."""

import json
from pathlib import Path

from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.util import sha256_text
from adversary.search.context import MinedSeed


class SeedStore(FrozenModel):
    """Validated harvest; ancestry must be attested separately by the miner."""

    records: tuple[MinedSeed, ...] = Field(min_length=1)
    digest: str

    @model_validator(mode="after")
    def unique_records(self) -> "SeedStore":
        keys = [(s.instance_id, s.base_commit, s.repo, s.miner, s.sha) for s in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate mined seed")
        return self

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "SeedStore":
        text = Path(path).read_text()
        records = tuple(
            MinedSeed.model_validate(json.loads(line)) for line in text.splitlines() if line.strip()
        )
        return cls(records=records, digest=sha256_text(text))

    def matching(self, instance_id: str, base_commit: str) -> tuple[MinedSeed, ...]:
        """Bind to both task identity and immutable base, never just the project name."""
        return tuple(
            s for s in self.records if s.instance_id == instance_id and s.base_commit == base_commit
        )
