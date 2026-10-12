"""Tests for projecting PDF paragraph boundaries onto canonical text."""

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.text_alignment import (  # noqa: E402
    align_pdf_paragraphs,
    align_structural_units,
    normalized_text_with_offsets,
)


class TextAlignmentTest(unittest.TestCase):
    def test_docx_list_item_aligns_as_one_canonical_block(self):
        canonical = "Before  Step therapy sequences are enforced while denying others.  After"
        result = align_structural_units(
            canonical_text=canonical,
            structure={
                "parser": "python-docx", "parser_version": "test", "warnings": [],
                "units": [{
                    "text": "Step therapy sequences are enforced while denying others.",
                    "type_hint": "list-item",
                }],
            },
        )
        list_blocks = [
            block for block in result["blocks"]
            if block["block_type"] == "list-item"
        ]
        self.assertEqual(1, len(list_blocks))
        self.assertEqual(
            "Step therapy sequences are enforced while denying others.",
            list_blocks[0]["plain_text"],
        )
    def test_normalization_maps_to_original_offsets(self):
        normalized, offsets = normalized_text_with_offsets(text="One  two\nthree")
        self.assertEqual("One two three", normalized)
        self.assertEqual("two", "One  two\nthree"[offsets[4] : offsets[6] + 1])

    def test_projects_paragraphs_to_canonical_text(self):
        canonical_text = "I. Heading  First paragraph wraps here.  Second paragraph."
        structure = {
            "pages": [
                {
                    "page_number": 1,
                    "paragraphs": [
                        {"text": "I. Heading", "line_count": 1},
                        {"text": "First paragraph wraps here.", "line_count": 2},
                        {"text": "Second paragraph.", "line_count": 1},
                    ],
                }
            ]
        }
        result = align_pdf_paragraphs(
            canonical_text=canonical_text, pdf_structure=structure
        )
        self.assertEqual(3, len(result["blocks"]))
        self.assertEqual("heading", result["blocks"][0]["block_type"])
        self.assertEqual("First paragraph wraps here.", result["blocks"][1]["plain_text"])
        self.assertEqual([], result["warnings"])
        self.assertIsNone(result["parser"])

    def test_does_not_invent_unmatched_pdf_text(self):
        result = align_pdf_paragraphs(
            canonical_text="Canonical paragraph.",
            pdf_structure={
                "pages": [
                    {
                        "page_number": 1,
                        "paragraphs": [{"text": "Different text.", "line_count": 1}],
                    }
                ]
            },
        )
        self.assertEqual("Canonical paragraph.", result["blocks"][0]["plain_text"])
        self.assertEqual("unmatched-canonical", result["blocks"][0]["block_type"])
        self.assertEqual("exact_canonical_match_not_found", result["warnings"][0]["warning"])

    def test_preserves_internal_canonical_gaps_in_order(self):
        result = align_pdf_paragraphs(
            canonical_text="Header  Page 1  Body paragraph.",
            pdf_structure={
                "parser": "pypdf",
                "parser_version": "test",
                "page_count": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "paragraphs": [
                            {"text": "Header", "line_count": 1},
                            {"text": "Body paragraph.", "line_count": 1},
                        ],
                    }
                ],
            },
        )
        self.assertEqual(
            ["Header", "Page 1", "Body paragraph."],
            [block["plain_text"] for block in result["blocks"]],
        )
        self.assertEqual("canonical_gap_preserved", result["blocks"][1]["alignment_method"])


if __name__ == "__main__":
    unittest.main(verbosity=2)