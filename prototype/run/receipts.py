"""File-integrity receipts and bounds for partially labeled verification runs."""

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "MANIFEST.json"


def build_manifest(directory: str | Path) -> dict:
    """List every regular file except the root manifest; refuse symbolic links."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("receipt directory does not exist")
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("receipt contains a symbolic link")
        if path == root / MANIFEST_NAME:
            continue
        if path.is_file():
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            entries.append({
                "path": path.relative_to(root).as_posix(),
                "size": size,
                "sha256": digest.hexdigest(),
            })
    return {"files": entries}


def write_manifest(directory: str | Path) -> Path:
    """Create a manifest without overwriting an existing receipt."""
    manifest = build_manifest(directory)
    target = Path(directory) / MANIFEST_NAME
    with target.open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
    return target


def verify_manifest(directory: str | Path) -> list[str]:
    """Return missing, unlisted or changed files; malformed manifests raise."""
    root = Path(directory)
    recorded = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(recorded, dict) or set(recorded) != {"files"}:
        raise ValueError("invalid manifest object")
    if not isinstance(recorded["files"], list):
        raise ValueError("invalid file list")
    expected = {}
    for entry in recorded["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ValueError("invalid file entry")
        name, size, digest = entry["path"], entry["size"], entry["sha256"]
        if (
            not isinstance(name, str)
            or not name
            or name.startswith("/")
            or "\\" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or name == MANIFEST_NAME
            or name in expected
        ):
            raise ValueError("invalid or duplicate file path")
        if type(size) is not int or size < 0:
            raise ValueError("invalid file size")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("invalid SHA-256 digest")
        expected[name] = entry
    current = {entry["path"]: entry for entry in build_manifest(root)["files"]}
    problems = []
    for name in sorted(expected.keys() | current.keys()):
        if name not in current:
            problems.append("missing: " + name)
        elif name not in expected:
            problems.append("unlisted: " + name)
        elif current[name] != expected[name]:
            problems.append("changed: " + name)
    return problems


def identification_bounds(
    verified: int, known_invalid: int, unknown: int
) -> tuple[float, float] | None:
    """Return [k/N, (k+u)/N]; an empty selection has no defined rate."""
    counts = (verified, known_invalid, unknown)
    if any(type(count) is not int or count < 0 for count in counts):
        raise ValueError("counts must be nonnegative integers")
    total = sum(counts)
    if total == 0:
        return None
    return verified / total, (verified + unknown) / total
