"""Tests for readable logical-document source selection."""

import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.document_selection import select_logical_documents  # noqa: E402


def _asset(*, key, suffix, role="markdown-source"):
    return {
        "source_object_key": key,
        "source_sha256": key,
        "source_suffix": suffix,
        "source_role": role,
        "markdown_path": f"{key}.md",
    }


class DocumentSelectionTest(unittest.TestCase):
    def test_selects_comment_body_and_excludes_metadata_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            comment_key = "raw/comments/COMMENT-1.json"
            metadata_key = "raw/documents/DOCUMENT-1.json"
            for key, value in (
                (
                    comment_key,
                    {"data": {"attributes": {"comment": "Public comment."}}},
                ),
                (
                    metadata_key,
                    {"data": {"attributes": {"comment": None, "title": "Rule"}}},
                ),
            ):
                path = source_root / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
            selected, decisions = select_logical_documents(
                source_root=source_root,
                assets=[
                    _asset(key=comment_key, suffix=".json"),
                    _asset(key=metadata_key, suffix=".json"),
                ],
            )
            self.assertEqual([comment_key], [asset["source_object_key"] for asset in selected])
            self.assertEqual("data.attributes.comment", selected[0]["content_location"])
            self.assertEqual("metadata-only-json", decisions[1]["selection_reason"])

    def test_selects_html_and_extracted_text_but_not_pdf(self):
        assets = [
            _asset(key="rule.html", suffix=".html"),
            _asset(key="attachment.txt", suffix=".txt"),
            _asset(key="attachment.pdf", suffix=".pdf", role="structural-source"),
        ]
        selected, decisions = select_logical_documents(
            source_root=Path("/unused"), assets=assets
        )
        self.assertEqual(
            ["rule.html", "attachment.txt"],
            [asset["source_object_key"] for asset in selected],
        )
        self.assertEqual("structural-source-only", decisions[2]["selection_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)