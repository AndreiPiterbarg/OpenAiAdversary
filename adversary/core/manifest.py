"""Content manifests for directories whose payloads stay out of git.

``data/`` and ``experiments/*/results/`` hold large or regenerable files. A
:class:`Manifest` records every file's size and SHA-256 so the manifest can be committed
in place of the payload and later verified against a re-created copy.
"""

from datetime import datetime
from pathlib import Path

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.util import sha256_bytes, sha256_json, utc_now

MANIFEST_NAME = "MANIFEST.json"


class FileEntry(FrozenModel):
    """One file in a manifest."""

    path: str = Field(description="Path relative to the manifest's directory, POSIX separators")
    size: int = Field(ge=0)
    sha256: str


class Manifest(FrozenModel):
    """Content listing of a directory."""

    produced_at: datetime = Field(default_factory=utc_now)
    files: tuple[FileEntry, ...]
    note: str = Field(
        default="", description="Free text: what the payload is and how to rebuild it"
    )

    def digest(self) -> str:
        """Hash of the file listing alone, independent of ``produced_at``."""
        return sha256_json([f.model_dump(mode="json") for f in self.files])

    def write(self, directory: str | Path) -> Path:
        """Write this manifest as ``MANIFEST.json`` inside ``directory``."""
        target = Path(directory) / MANIFEST_NAME
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target

    @classmethod
    def read(cls, directory: str | Path) -> "Manifest":
        """Load ``MANIFEST.json`` from ``directory``."""
        return cls.model_validate_json(
            (Path(directory) / MANIFEST_NAME).read_text(encoding="utf-8")
        )


def build_manifest(directory: str | Path, note: str = "") -> Manifest:
    """Hash every regular file under ``directory`` except the manifest itself."""
    root = Path(directory)
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST_NAME):
        data = path.read_bytes()
        entries.append(
            FileEntry(
                path=path.relative_to(root).as_posix(), size=len(data), sha256=sha256_bytes(data)
            )
        )
    return Manifest(files=tuple(entries), note=note)


def verify_manifest(directory: str | Path) -> list[str]:
    """Compare a directory with its manifest.

    Returns:
        Human-readable discrepancies; empty means the payload matches the manifest exactly.
    """
    root = Path(directory)
    recorded = Manifest.read(root)
    current = build_manifest(root)
    by_path_recorded = {f.path: f for f in recorded.files}
    by_path_current = {f.path: f for f in current.files}
    problems = []
    for path in sorted(set(by_path_recorded) | set(by_path_current)):
        if path not in by_path_current:
            problems.append(f"missing: {path}")
        elif path not in by_path_recorded:
            problems.append(f"unlisted: {path}")
        elif by_path_recorded[path].sha256 != by_path_current[path].sha256:
            problems.append(f"changed: {path}")
    return problems
