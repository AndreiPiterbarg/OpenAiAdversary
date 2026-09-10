"""The accumulating private library of probes: one JSON file per probe.

The library refuses probes whose programs were authored by a restricted-licence model. That
check is the shipping gate for generators, the counterpart of the repair layer's check on
trajectories. :class:`LicenseError` lives in ``adversary.core.model`` and is re-exported here.
"""

from collections.abc import Iterator
from pathlib import Path

from adversary.core.model import LicenseError
from adversary.probe.probe import Probe


class ProbeLibrary:
    """Directory-backed probe store."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, probe_id: str) -> Path:
        return self.directory / f"{probe_id}.json"

    def add(self, probe: Probe) -> Path:
        """Persist a probe; raises :class:`LicenseError` if it cannot be shipped."""
        if not probe.shippable:
            raise LicenseError(
                f"probe {probe.id} was authored by {probe.provenance.authored_by} "
                "under a restricted licence"
            )
        path = self._path(probe.id)
        path.write_text(probe.model_dump_json(indent=2), encoding="utf-8")
        return path

    def get(self, probe_id: str) -> Probe:
        """Load one probe."""
        return Probe.model_validate_json(self._path(probe_id).read_text(encoding="utf-8"))

    def ids(self) -> list[str]:
        """All stored probe ids, sorted."""
        return sorted(p.stem for p in self.directory.glob("probe_*.json"))

    def __iter__(self) -> Iterator[Probe]:
        return (self.get(i) for i in self.ids())

    def __len__(self) -> int:
        return len(self.ids())

    def __contains__(self, probe_id: object) -> bool:
        return isinstance(probe_id, str) and self._path(probe_id).exists()


__all__ = ["LicenseError", "ProbeLibrary"]
