"""Tests for clean semantic Markdown conversion."""

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.semantic_document import (  # noqa: E402
    html_to_semantic_blocks, render_semantic_markdown,
)


class SemanticDocumentTest(unittest.TestCase):
    def test_no_break_tag_permutation_survives(self):
        source = "One<br>Two<br/>Three<br />Four</br>Five<BR>Six\r\nSeven\rEight\x00"
        blocks = html_to_semantic_blocks(html_text=source)
        markdown = render_semantic_markdown(blocks=blocks)
        for forbidden in ("<br", "</br>", "\r", "\x00"):
            self.assertNotIn(forbidden, markdown.lower())
            self.assertTrue(all(forbidden not in block["plain_text"].lower() for block in blocks))

    def test_models_sections_labels_lists_quotes_and_tables(self):
        source = (
            "I. Heading<br>Prose has two sentences. It remains one paragraph.<br>"
            "Recommendation:<br>&bull; First item<br>"
            "<blockquote>Quoted text.</blockquote>"
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        )
        blocks = html_to_semantic_blocks(html_text=source)
        self.assertEqual(
            ["section", "paragraph", "label", "list-item", "quotation", "table"],
            [block["block_type"] for block in blocks],
        )
        self.assertEqual("section-0001", blocks[0]["block_id"])
        self.assertEqual("paragraph-0001", blocks[1]["block_id"])
        self.assertEqual("list-item-0001", blocks[3]["block_id"])
        self.assertEqual("table-0001", blocks[5]["block_id"])
        self.assertNotIn("table-row", render_semantic_markdown(blocks=blocks))

    def test_real_form_comment_has_semantic_paragraphs_and_lists(self):
        fixture_path = (
            Path(__file__).parent / "fixtures" / "regression_cases"
            / "CMS-2026-1255-0028" / "source" / "CMS-2026-1255-0028.json"
        )
        comment_html = json.loads(fixture_path.read_text(encoding="utf-8"))[
            "data"
        ]["attributes"]["comment"]
        blocks = html_to_semantic_blocks(html_text=comment_html)
        markdown = render_semantic_markdown(blocks=blocks)
        block_types = [block["block_type"] for block in blocks]
        self.assertGreater(block_types.count("paragraph"), 8)
        self.assertEqual(4, block_types.count("section"))
        self.assertEqual(9, block_types.count("list-item"))
        self.assertGreaterEqual(block_types.count("label"), 3)
        self.assertIn('<a id="section-0001"></a>', markdown)
        self.assertIn('<a id="paragraph-0001"></a>', markdown)
        self.assertIn('<a id="list-item-0001"></a>', markdown)
        self.assertNotRegex(markdown, r"(?i)</?br\b")


if __name__ == "__main__":
    unittest.main(verbosity=2)