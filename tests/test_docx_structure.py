"""Fixture tests for DOCX semantic structure extraction."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.docx_structure import extract_docx_structure  # noqa: E402


class DocxStructureTest(unittest.TestCase):
    def test_real_docx_preserves_paragraphs_and_lists(self):
        path = (
            Path(__file__).parent / "fixtures/regression_cases/"
            "CMS-2026-1255-0008-attachment-1/source/"
            "CMS-2026-1255-0008_attachment_1.docx"
        )
        structure = extract_docx_structure(docx_path=path)
        types = [unit["type_hint"] for unit in structure["units"]]
        self.assertGreater(len(structure["units"]), 50)
        self.assertGreaterEqual(types.count("list-item"), 17)
        step_items = [
            unit for unit in structure["units"]
            if unit["text"].startswith("Step therapy sequences")
        ]
        self.assertEqual(1, len(step_items))
        self.assertIn("while denying others", step_items[0]["text"])
        self.assertEqual("list-item", step_items[0]["type_hint"])


if __name__ == "__main__":
    unittest.main(verbosity=2)