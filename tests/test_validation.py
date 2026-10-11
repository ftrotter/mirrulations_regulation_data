"""Tests for reusable corpus validation utilities."""

import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.pipeline import STAGE_1, STAGE_2  # noqa: E402
from mirrulations_markdown.validation import (  # noqa: E402
    capture_tree_hashes,
    compare_tree_hashes,
    read_hash_snapshot,
    tree_hash,
    write_hash_snapshot,
)


class TreeHashTest(unittest.TestCase):
    def test_hash_is_stable_and_changes_with_file_bytes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            file_path = root_path / "nested" / "document.md"
            file_path.parent.mkdir()
            file_path.write_text("first\n", encoding="utf-8")
            first_hash = tree_hash(root_path=root_path)
            self.assertEqual(first_hash, tree_hash(root_path=root_path))
            file_path.write_text("second\n", encoding="utf-8")
            self.assertNotEqual(first_hash, tree_hash(root_path=root_path))

    def test_relative_paths_affect_hash(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            first_path = root_path / "first.txt"
            first_path.write_text("same", encoding="utf-8")
            first_hash = tree_hash(root_path=root_path)
            first_path.rename(root_path / "second.txt")
            self.assertNotEqual(first_hash, tree_hash(root_path=root_path))


class SnapshotTest(unittest.TestCase):
    def test_snapshot_round_trip_and_comparison(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            snapshot_path = Path(temporary_directory) / "snapshot.json"
            expected = {"source": "abc", "stage001": "def"}
            write_hash_snapshot(output_path=snapshot_path, tree_hashes=expected)
            actual = read_hash_snapshot(snapshot_path=snapshot_path)
            self.assertEqual(expected, actual)
            self.assertEqual(
                [], compare_tree_hashes(before_hashes=expected, after_hashes=actual)
            )
            self.assertEqual(
                ["source"],
                compare_tree_hashes(
                    before_hashes=expected,
                    after_hashes={"source": "changed", "stage001": "def"},
                ),
            )

    def test_capture_requires_all_three_trees(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            source_root = root_path / "source"
            markdown_db_path = root_path / "markdown"
            source_root.mkdir()
            (markdown_db_path / STAGE_1).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "stage002"):
                capture_tree_hashes(
                    source_root=source_root, markdown_db_path=markdown_db_path
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)