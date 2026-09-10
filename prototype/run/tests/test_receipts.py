import json
import tempfile
import unittest
from pathlib import Path

from prototype.run.receipts import identification_bounds, verify_manifest, write_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "test.log").write_text("PASSED test_example\n")
        self.manifest = write_manifest(self.root)

    def test_unchanged_receipt_verifies(self):
        self.assertEqual(verify_manifest(self.root), [])

    def test_changed_missing_and_unlisted_files(self):
        (self.root / "test.log").write_text("FAILED test_example\n")
        self.assertEqual(verify_manifest(self.root), ["changed: test.log"])
        (self.root / "test.log").unlink()
        (self.root / "extra.log").write_text("extra")
        self.assertEqual(
            verify_manifest(self.root), ["unlisted: extra.log", "missing: test.log"]
        )

    def test_manifest_is_not_overwritten(self):
        original = self.manifest.read_bytes()
        with self.assertRaises(FileExistsError):
            write_manifest(self.root)
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_recorded_size_is_checked(self):
        data = json.loads(self.manifest.read_text())
        data["files"][0]["size"] += 1
        self.manifest.write_text(json.dumps(data))
        self.assertEqual(verify_manifest(self.root), ["changed: test.log"])

    def test_unsafe_and_duplicate_paths_are_refused(self):
        original = json.loads(self.manifest.read_text())
        for name in ["../test.log", "/test.log", "a/../test.log", "", "a//b"]:
            with self.subTest(name=name):
                data = json.loads(json.dumps(original))
                data["files"][0]["path"] = name
                self.manifest.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    verify_manifest(self.root)
        original["files"].append(original["files"][0])
        self.manifest.write_text(json.dumps(original))
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_symbolic_links_are_refused(self):
        (self.root / "alias.log").symlink_to(self.root / "test.log")
        with self.assertRaises(ValueError):
            verify_manifest(self.root)

    def test_nested_files_are_included(self):
        self.manifest.unlink()
        nested = self.root / "baseline"
        nested.mkdir()
        (nested / "MANIFEST.json").write_text("{}")
        write_manifest(self.root)
        (nested / "MANIFEST.json").write_text('{"changed": true}')
        self.assertEqual(verify_manifest(self.root), ["changed: baseline/MANIFEST.json"])


class BoundsTests(unittest.TestCase):
    def test_unknowns_remain_in_denominator(self):
        self.assertEqual(identification_bounds(2, 3, 5), (0.2, 0.7))

    def test_all_unknown_and_fully_labeled(self):
        self.assertEqual(identification_bounds(0, 0, 10), (0.0, 1.0))
        self.assertEqual(identification_bounds(2, 8, 0), (0.2, 0.2))

    def test_empty_selection(self):
        self.assertIsNone(identification_bounds(0, 0, 0))

    def test_invalid_counts(self):
        for bad in [-1, True, 1.5, "1"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                identification_bounds(bad, 0, 0)


if __name__ == "__main__":
    unittest.main()
