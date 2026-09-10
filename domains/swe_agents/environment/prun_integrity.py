"""Strict receipt byte authentication, without executing producer code."""

import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Never

from domains.swe_agents.environment.gold import digest


def strict_json(text: str) -> dict | list:
    def pairs(items: list[tuple[str, object]]) -> dict:
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key: " + key)
            value[key] = item
        return value

    def constant(value: str) -> Never:
        raise ValueError("nonfinite JSON value: " + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def regular_files(root: Path) -> list[Path]:
    files = []
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.is_symlink():
                raise ValueError("symlink receipt file")
            if entry.is_dir(follow_symlinks=False):
                files.extend(regular_files(Path(entry.path)))
            elif entry.is_file(follow_symlinks=False):
                files.append(Path(entry.path))
            else:
                raise ValueError("nonregular receipt file")
    return files


def require_regular(path: Path) -> None:
    # Inspect every component before resolving; an intermediate link is equally
    # capable of redirecting an otherwise relative authenticated path.
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("symlink receipt path")
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("nonregular receipt file")
    except FileNotFoundError as exc:
        raise ValueError("required manifest file missing") from exc


class Receipt:
    def __init__(self, root: Path, anchor: str) -> None:
        require_regular(root.absolute() / "MANIFEST.json")
        self.root = root.resolve()
        if not re.fullmatch("[0-9a-f]{64}", anchor):
            raise ValueError("invalid root manifest digest")
        manifest_path = self.root / "MANIFEST.json"
        if manifest_path.is_symlink() or digest(manifest_path) != anchor:
            raise ValueError("root manifest digest mismatch")
        manifest = strict_json(manifest_path.read_text())
        self.entries = {}
        actual = {
            path.relative_to(self.root).as_posix()
            for path in regular_files(self.root)
            if path != manifest_path
        }
        for entry in manifest["files"]:
            name = entry["path"]
            pure = PurePosixPath(name)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or name != pure.as_posix()
                or name in {"", ".", "MANIFEST.json"}
                or "\\" in name
                or name in self.entries
            ):
                raise ValueError("unsafe or duplicate manifest path")
            path = self.root / name
            if (
                name not in actual
                or type(entry["size"]) is not int
                or entry["size"] < 0
                or path.stat().st_size != entry["size"]
                or digest(path) != entry["sha256"]
            ):
                raise ValueError("receipt file differs from manifest: " + name)
            self.entries[name] = path
        # Legacy producers excluded every nested MANIFEST.json. Modern producers
        # include all of them. Mixed partial coverage is not an accepted policy.
        legacy = {name for name in actual if PurePosixPath(name).name != "MANIFEST.json"}
        if set(self.entries) not in (actual, legacy):
            raise ValueError("manifest does not cover receipt files exactly")
        # Even legacy unsigned nested manifests must faithfully describe their
        # files; they never authorize a file absent from the trusted root.
        for name in actual:
            if PurePosixPath(name).name != "MANIFEST.json":
                continue
            directory = (self.root / name).parent
            nested = strict_json((self.root / name).read_text())
            seen = set()
            for entry in nested["files"]:
                child = entry["path"]
                p = PurePosixPath(child)
                if p.is_absolute() or ".." in p.parts or child != p.as_posix() or child in seen:
                    raise ValueError("unsafe or duplicate nested manifest path")
                seen.add(child)
                full = (directory / child).relative_to(self.root).as_posix()
                if full not in self.entries:
                    raise ValueError("nested manifest references unauthenticated file")
                path = self.entries[full]
                if (
                    type(entry["size"]) is not int
                    or entry["size"] < 0
                    or path.stat().st_size != entry["size"]
                    or digest(path) != entry["sha256"]
                ):
                    raise ValueError("nested manifest differs from authenticated file")
            expected = {
                p.relative_to(directory).as_posix()
                for p in regular_files(directory)
                if p.is_file() and p.name != "MANIFEST.json"
            }
            if seen != expected:
                raise ValueError("nested manifest coverage mismatch")

    def read(self, name: str) -> str:
        if name not in self.entries:
            raise ValueError("required file absent from manifest: " + name)
        return self.entries[name].read_bytes().decode("utf-8")

    def obj(self, name: str) -> dict | list:
        return strict_json(self.read(name))
