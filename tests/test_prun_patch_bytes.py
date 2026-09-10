"""Authenticated patch text must retain its original line endings."""

from pathlib import Path

from adversary.core.manifest import build_manifest
from domains.swe_agents.environment.gold import digest
from domains.swe_agents.environment.prun_integrity import Receipt


def test_authenticated_patch_preserves_crlf(tmp_path: Path) -> None:
    patch = b"diff --git a/file.py b/file.py\r\n--- a/file.py\r\n+++ b/file.py\r\n"
    (tmp_path / "gold.patch").write_bytes(patch)
    build_manifest(tmp_path).write(tmp_path)
    receipt = Receipt(tmp_path, digest(tmp_path / "MANIFEST.json"))

    assert receipt.read("gold.patch") == patch.decode("utf-8")
    assert receipt.read("gold.patch").encode("utf-8") == patch
