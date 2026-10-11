"""Tests for global citation reverse lookup generation."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.reverse_lookup import write_citation_reverse_lookup  # noqa: E402


class ReverseLookupTest(unittest.TestCase):
    def test_groups_and_deduplicates_occurrences(self):
        citation = {
            "normalized_target": "cfr:42:482.24", "resolution_status": "resolved",
            "markdown_path": "comments/a.md", "block_id": "p-0007",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lookup.md"
            write_citation_reverse_lookup(
                output_path=path, citations=[citation, citation],
                reference_names={"cfr:42:482.24": "Medical record services"},
                document_names={"comments/a.md": "AGA comments"},
            )
            text = path.read_text()
            self.assertEqual(1, text.count("[AGA comments]"))
            self.assertIn("comments/a.md#p-0007", text)

    def test_includes_unresolved_citation(self):
        citation = {
            "normalized_target": "eyecite:fullcasecitation:hash",
            "resolution_status": "unresolved",
            "markdown_path": "comments/a.md", "block_id": "p-0008",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lookup.md"
            write_citation_reverse_lookup(
                output_path=path, citations=[citation],
                reference_names={
                    "eyecite:fullcasecitation:hash": "Foo v. Bar, 1 U.S. 2"
                },
                document_names={"comments/a.md": "AGA comments"},
            )
            text = path.read_text()
            self.assertIn("## Foo v. Bar, 1 U.S. 2", text)
            self.assertIn("comments/a.md#p-0008", text)


if __name__ == "__main__": unittest.main(verbosity=2)