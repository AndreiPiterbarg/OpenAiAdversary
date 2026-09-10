"""Append-only episode storage.

Every episode the harness records goes here as one JSON line, alongside its trajectory and
alongside every instance that produced no episode. The store is the evidence base: kill
records, confirmation receipts and pre-registered results all cite episode ids and the store
digest, so a claim can be traced back to the rows that produced it. Writes are serialised
with a lock so a parallel harness cannot interleave lines.
"""

import json
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path

from adversary.core.episode import Episode, Unreached
from adversary.core.model import LicenseClass
from adversary.core.trajectory import Trajectory
from adversary.core.util import sha256_bytes, short_id

EPISODES_FILE = "episodes.jsonl"
UNREACHED_FILE = "unreached.jsonl"
TRAJECTORIES_FILE = "trajectories.jsonl"


class EpisodeStore:
    """A directory of ``episodes.jsonl``, ``trajectories.jsonl`` and ``unreached.jsonl``."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._episodes = self.directory / EPISODES_FILE
        self._unreached = self.directory / UNREACHED_FILE
        self._trajectories = self.directory / TRAJECTORIES_FILE
        self._lock = threading.Lock()
        self._trajectory_offsets: dict[str, int] = {}
        self._trajectory_scanned = 0

    def append(self, episode: Episode, trajectory: Trajectory | None = None) -> None:
        """Persist one episode and, if given, its trajectory (keyed by episode id)."""
        with self._lock:
            with open(self._episodes, "a", encoding="utf-8") as handle:
                handle.write(episode.model_dump_json() + "\n")
            if trajectory is not None:
                record = {
                    "episode_id": episode.id,
                    "trajectory": trajectory.model_dump(mode="json"),
                }
                with open(self._trajectories, "a", encoding="utf-8") as handle:
                    offset = handle.tell()
                    handle.write(json.dumps(record) + "\n")
                self._trajectory_offsets[episode.id] = offset

    def append_witness(
        self, instance_id: str, trajectory: Trajectory, *, producer_license: LicenseClass
    ) -> str:
        """Persist a reference (witness) trajectory that has no episode; returns its id."""
        witness_id = short_id("witness", [instance_id, trajectory.model_id, trajectory.steps])
        with self._lock, open(self._trajectories, "a", encoding="utf-8") as handle:
            offset = handle.tell()
            record = {
                "episode_id": witness_id,
                "trajectory": trajectory.model_dump(mode="json"),
                "producer_license": producer_license.value,
                "purpose": "witness_only",
            }
            handle.write(json.dumps(record) + "\n")
            self._trajectory_offsets[witness_id] = offset
        return witness_id

    def append_unreached(self, record: Unreached) -> None:
        """Persist one instance that produced no episode."""
        with self._lock, open(self._unreached, "a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")

    def _index_trajectories(self) -> None:
        """Rebuild the id -> byte-offset index from the file (handles external appends)."""
        if not self._trajectories.exists():
            return
        size = self._trajectories.stat().st_size
        if size == self._trajectory_scanned:
            return
        offsets: dict[str, int] = {}
        with open(self._trajectories, "rb") as handle:
            offset = 0
            for line in handle:
                if line.strip():
                    offsets[json.loads(line)["episode_id"]] = offset
                offset += len(line)
        self._trajectory_offsets = offsets
        self._trajectory_scanned = size

    def trajectory(self, episode_id: str) -> Trajectory | None:
        """The trajectory recorded for ``episode_id``, or ``None`` if none was stored."""
        with self._lock:
            if episode_id not in self._trajectory_offsets:
                self._index_trajectories()
            offset = self._trajectory_offsets.get(episode_id)
            if offset is None:
                return None
            with open(self._trajectories, "rb") as handle:
                handle.seek(offset)
                record = json.loads(handle.readline())
        return Trajectory.model_validate(record["trajectory"])

    def __iter__(self) -> Iterator[Episode]:
        if not self._episodes.exists():
            return iter(())
        with open(self._episodes, encoding="utf-8") as handle:
            return iter([Episode.model_validate_json(line) for line in handle if line.strip()])

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def unreached(self) -> list[Unreached]:
        """Every instance that produced no episode."""
        if not self._unreached.exists():
            return []
        with open(self._unreached, encoding="utf-8") as handle:
            return [Unreached.model_validate_json(line) for line in handle if line.strip()]

    def get(self, ids: Iterable[str]) -> list[Episode]:
        """Episodes with the given ids, in store order."""
        wanted = set(ids)
        return [e for e in self if e.id in wanted]

    def digest(self) -> str:
        """SHA-256 of the episode file; cited by receipts and kill records."""
        data = self._episodes.read_bytes() if self._episodes.exists() else b""
        return sha256_bytes(data)

    def has_ids(self, ids: Iterable[str]) -> bool:
        """Whether every id is present."""
        present = {e.id for e in self}
        return all(i in present for i in ids)

    def record_epoch(self, manifest: dict, release: dict) -> None:
        """Append complete frozen selection evidence without importing the search layer."""
        with self._lock, (self.directory / "epochs.jsonl").open("a") as handle:
            handle.write(
                json.dumps({"manifest": manifest, "release": release}, allow_nan=False) + "\n"
            )
