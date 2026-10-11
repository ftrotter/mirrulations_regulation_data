"""Tests for metadata extraction and persistent document names."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.friendly_metadata import (  # noqa: E402
    document_metadata, metadata_from_json, normalized_friendly_name,
    parse_markdown_table_row, write_document_friendly_names,
)


class FriendlyMetadataTest(unittest.TestCase):
    def test_parses_escaped_pipe_without_shifting_columns(self):
        self.assertEqual(
            ["PWSA | USA", "Human edit", "path.md"],
            parse_markdown_table_row(
                line="| PWSA \\| USA | Human edit | path.md |"
            ),
        )
    def test_name_template_omits_missing_parts(self):
        self.assertEqual(
            "AGA Jane Smith: Comment title",
            normalized_friendly_name(
                organization="AGA", person_name="Jane Smith", title="Comment title"
            ),
        )
        self.assertEqual(
            "Comment title",
            normalized_friendly_name(organization=None, person_name=None, title="Comment title"),
        )

    def test_extracts_comment_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comment.json"
            path.write_text(json.dumps({"data": {"id": "CMS-1", "attributes": {
                "docketId": "CMS-D", "title": "Title", "organization": "Org",
                "firstName": "Jane", "lastName": "Smith", "documentType": "Public Submission"
            }}}), encoding="utf-8")
            metadata = metadata_from_json(json_path=path)
            self.assertEqual("Jane Smith", metadata["person_name"])
            self.assertEqual("Org", metadata["organization"])

    def test_preserves_edited_document_name(self):
        with tempfile.TemporaryDirectory() as directory:
            table_path = Path(directory) / "names.md"
            documents = [{"generated_friendly_name": "Generated", "markdown_path": "a.md"}]
            write_document_friendly_names(table_path=table_path, documents=documents)
            table_path.write_text(table_path.read_text().replace("| Generated |  |", "| Generated | Human edit |"))
            names = write_document_friendly_names(table_path=table_path, documents=[
                {"generated_friendly_name": "Changed generated", "markdown_path": "a.md"}
            ])
            self.assertEqual("Human edit", names["a.md"])
            self.assertIn("| Changed generated | Human edit | a.md |", table_path.read_text())

    def test_pdf_attachment_metadata_includes_markdown_link(self):
        metadata = document_metadata(
            asset={"source_object_key": "derived/CMS-2026-1255-0009_attachment_1_extracted.txt"},
            metadata_records={
                "CMS-2026-1255-0009": {
                    "title": "Comment title", "organization": "Org",
                    "person_name": "", "authors": [],
                }
            },
            pairing={
                "structural_source_object_key": "raw/CMS-2026-1255-0009_attachment_1.pdf",
                "attachment_number": 1,
            },
        )
        self.assertEqual(
            "[original pdf](https://downloads.regulations.gov/"
            "CMS-2026-1255-0009/attachment_1.pdf)",
            metadata["original_pdf_link"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)