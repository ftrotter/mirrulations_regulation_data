"""Unit tests for pure PDF physical-line and paragraph grouping."""

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.pdf_structure import (  # noqa: E402
    _layout_lines,
    _paragraphs_from_lines,
)


class PdfStructureTest(unittest.TestCase):
    def test_layout_lines_preserve_blank_rows_and_indentation(self):
        lines = _layout_lines(layout_text="  Hello world\n\nNext\n")
        self.assertEqual("Hello world", lines[0]["text"])
        self.assertEqual(2, lines[0]["indent"])
        self.assertTrue(lines[1]["is_blank"])

    def test_vertical_gap_starts_new_paragraph(self):
        paragraphs = _paragraphs_from_lines(
            lines=[
                {"text": "First line", "indent": 0, "is_blank": False},
                {"text": "continues", "indent": 0, "is_blank": False},
                {"text": "", "indent": 0, "is_blank": True},
                {"text": "Second paragraph", "indent": 0, "is_blank": False},
            ]
        )
        self.assertEqual(2, len(paragraphs))
        self.assertEqual("First line continues", paragraphs[0]["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)