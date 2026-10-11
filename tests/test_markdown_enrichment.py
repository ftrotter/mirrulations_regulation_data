"""Tests for deterministic initial and citation-enriched Markdown stages."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.configuration import (  # noqa: E402
    DEFAULT_MARKDOWN_DB_PATH,
    load_paths,
    validate_separate_roots,
)
from mirrulations_markdown.conversion import html_to_markdown, json_to_markdown  # noqa: E402
from mirrulations_markdown.pipeline import MarkdownPipeline, STAGE_1, STAGE_2  # noqa: E402
from mirrulations_markdown.verification import (  # noqa: E402
    _comparison_counts,
    docket_include_patterns,
    require_verified_manifest,
)


class ConfigurationTest(unittest.TestCase):
    def test_rejects_nested_roots(self):
        with self.assertRaisesRegex(ValueError, "non-overlapping"):
            validate_separate_roots(
                source_root="/tmp/source", markdown_db_path="/tmp/source/generated"
            )

    def test_uses_repository_default_markdown_database(self):
        with tempfile.TemporaryDirectory() as source_directory:
            source_root, markdown_db_path = load_paths(source_root=source_directory)
        self.assertEqual(Path(source_directory).resolve(), source_root)
        self.assertEqual(DEFAULT_MARKDOWN_DB_PATH.resolve(), markdown_db_path)


class ConversionTest(unittest.TestCase):
    def test_html_preserves_structure_and_links_without_scripts(self):
        markdown = html_to_markdown(
            html_text=(
                "<h2>Requirements</h2><p>See <a href='https://example.test'>"
                "the source</a>.\x00</p><script>do_not_include()</script><ul><li>One</li></ul>"
            )
        )
        self.assertIn("## Requirements", markdown)
        self.assertIn("[the source](https://example.test)", markdown)
        self.assertIn("- One", markdown)
        self.assertNotIn("do_not_include", markdown)
        self.assertNotIn("\x00", markdown)

    def test_json_prefers_nested_content(self):
        markdown, json_path = json_to_markdown(
            json_text=json.dumps({"data": {"attributes": {"content": "Hello."}}})
        )
        self.assertEqual("Hello.\n", markdown)
        self.assertEqual("data.attributes.content", json_path)


class VerificationTest(unittest.TestCase):
    def test_builds_text_only_docket_patterns(self):
        patterns = docket_include_patterns(
            docket_id="CMS-2026-1255", text_only=True
        )
        self.assertEqual(8, len(patterns))
        self.assertIn(
            "/raw-data/CMS/CMS-2026-1255/**/*.htm", patterns
        )
        self.assertIn(
            "/derived-data/CMS/CMS-2026-1255/**/*.txt", patterns
        )
        self.assertIn(
            "/raw-data/CMS/CMS-2026-1255/**/*.html", patterns
        )

    def test_full_docket_patterns_include_all_objects(self):
        self.assertEqual(
            [
                "/raw-data/CMS/CMS-2026-1255/**/*",
                "/derived-data/CMS/CMS-2026-1255/**/*",
            ],
            docket_include_patterns(docket_id="CMS-2026-1255"),
        )

    def test_parses_missing_differing_and_unexpected_objects(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "combined.txt"
            report_path.write_text(
                "= raw-data/match.txt\n- raw-data/missing.txt\n"
                "* raw-data/different.txt\n+ raw-data/unexpected.txt\n",
                encoding="utf-8",
            )
            self.assertEqual(
                {"matching": 1, "missing": 1, "differing": 1, "unexpected": 1},
                _comparison_counts(combined_path=report_path),
            )

    def test_requires_manifest_for_the_same_source_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            source_root.mkdir()
            manifest_path = temporary_root / "verification.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "verified": True,
                        "text_only": False,
                        "source_root": str(source_root.resolve()),
                        "docket_id": "CMS-2026-1255",
                        "source_inventory_fingerprint": (
                            "e3b0c44298fc1c149afbf4c8996fb924"
                            "27ae41e4649b934ca495991b7852b855"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            manifest = require_verified_manifest(
                manifest_path=manifest_path,
                source_root=source_root,
                docket_id="CMS-2026-1255",
            )
            self.assertTrue(manifest["verified"])

    def test_rejects_unverified_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            source_root.mkdir()
            manifest_path = temporary_root / "verification.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "verified": False,
                        "text_only": False,
                        "source_root": str(source_root),
                        "docket_id": "CMS-2026-1255",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not verified"):
                require_verified_manifest(
                    manifest_path=manifest_path,
                    source_root=source_root,
                    docket_id="CMS-2026-1255",
                )

    def test_rejects_manifest_for_another_docket(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            source_root.mkdir()
            manifest_path = temporary_root / "verification.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "verified": True,
                        "text_only": False,
                        "source_root": str(source_root.resolve()),
                        "docket_id": "CMS-2026-1255",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "another docket"):
                require_verified_manifest(
                    manifest_path=manifest_path,
                    source_root=source_root,
                    docket_id="CMS-2026-9999",
                )


class PipelineTest(unittest.TestCase):
    def test_builds_both_stages_with_provenance_and_citation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            markdown_db_path = temporary_root / "markdown_db"
            source_file = (
                source_root
                / "raw-data"
                / "CMS"
                / "CMS-2026-1255"
                / "text-CMS-2026-1255"
                / "documents"
                / "CMS-2026-1255-0001_content.htm"
            )
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                "<h1>Proposed Rule</h1><p>Authority includes 5 U.S.C. § 553.</p>",
                encoding="utf-8",
            )
            source_bytes_before = source_file.read_bytes()

            first_status = MarkdownPipeline.run(
                source_root=source_root,
                markdown_db_path=markdown_db_path,
                docket_id="CMS-2026-1255",
            )
            output_relative_path = Path(
                "raw-data/CMS/CMS-2026-1255/text-CMS-2026-1255/documents/"
                "CMS-2026-1255-0001_content.htm.md"
            )
            stage_1_path = markdown_db_path / STAGE_1 / output_relative_path
            stage_2_path = markdown_db_path / STAGE_2 / output_relative_path
            stage_1_before = stage_1_path.read_bytes()
            stage_2_before = stage_2_path.read_bytes()

            second_status = MarkdownPipeline.run(
                source_root=source_root,
                markdown_db_path=markdown_db_path,
                docket_id="CMS-2026-1255",
            )

            self.assertEqual(0, first_status["failed_asset_count"])
            self.assertEqual(first_status, second_status)
            self.assertEqual(source_bytes_before, source_file.read_bytes())
            self.assertEqual(stage_1_before, stage_1_path.read_bytes())
            self.assertEqual(stage_2_before, stage_2_path.read_bytes())
            self.assertIn("source_sha256:", stage_1_path.read_text(encoding="utf-8"))
            self.assertIn(
                "[5 U.S.C. § 553](https://www.law.cornell.edu/uscode/text/5/553)",
                stage_2_path.read_text(encoding="utf-8"),
            )
            self.assertTrue(
                all(
                    result["adapter_name"] == "eyecite"
                    and result["status"] == "success"
                    for result in first_status["adapter_results"]
                )
            )
            inventory = json.loads(
                (markdown_db_path / "metadata/manifests/source_inventory.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(1, len(inventory["assets"]))
            self.assertEqual("not-applicable", inventory["assets"][0]["structure_status"])

    @mock.patch("mirrulations_markdown.pipeline.extract_pdf_structure")
    def test_pdf_pairing_renders_multiple_canonical_blocks(self, extract_structure):
        extract_structure.return_value = {
            "parser": "pypdf",
            "parser_version": "test",
            "page_count": 1,
            "pages": [
                {
                    "page_number": 1,
                    "paragraphs": [
                        {"text": "I. Heading", "line_count": 1},
                        {"text": "First paragraph.", "line_count": 2},
                        {"text": "Second paragraph.", "line_count": 1},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            markdown_db_path = temporary_root / "markdown"
            canonical_path = (
                source_root / "derived-data/CMS/CMS-2026-1255/tool/"
                "comments_extracted_text/pypdf/"
                "CMS-2026-1255-0002_attachment_1_extracted.txt"
            )
            pdf_path = (
                source_root / "raw-data/CMS/CMS-2026-1255/binary/"
                "comments_attachments/CMS-2026-1255-0002_attachment_1.pdf"
            )
            canonical_path.parent.mkdir(parents=True)
            pdf_path.parent.mkdir(parents=True)
            canonical_path.write_text(
                "I. Heading  First paragraph.  Second paragraph.", encoding="utf-8"
            )
            pdf_path.write_bytes(b"synthetic structural source")
            status = MarkdownPipeline.run(
                source_root=source_root,
                markdown_db_path=markdown_db_path,
                docket_id="CMS-2026-1255",
            )
            output_path = (
                markdown_db_path / STAGE_1
                / canonical_path.relative_to(source_root).with_name(
                    f"{canonical_path.name}.md"
                )
            )
            output = output_path.read_text(encoding="utf-8")
            self.assertEqual(0, status["failed_asset_count"])
            self.assertIn("## I. Heading", output)
            self.assertIn('<a id="p-0003"></a>', output)
            self.assertIn("structural_source_object_key:", output)

    def test_metadata_json_is_not_rendered_and_stale_projection_is_pruned(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "source"
            markdown_db_path = temporary_root / "markdown"
            metadata_path = (
                source_root / "raw-data/CMS/CMS-2026-1255/documents/rule.json"
            )
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text(
                json.dumps({"data": {"attributes": {"comment": None, "title": "Rule"}}}),
                encoding="utf-8",
            )
            stale_path = (
                markdown_db_path / STAGE_1
                / metadata_path.relative_to(source_root).with_name("rule.json.md")
            )
            stale_path.parent.mkdir(parents=True)
            stale_path.write_text("stale", encoding="utf-8")
            status = MarkdownPipeline.run(
                source_root=source_root,
                markdown_db_path=markdown_db_path,
                docket_id="CMS-2026-1255",
            )
            self.assertEqual(0, status["markdown_asset_count"])
            self.assertFalse(stale_path.exists())
            decisions = json.loads(
                (
                    markdown_db_path
                    / "metadata/manifests/document_selection.json"
                ).read_text(encoding="utf-8")
            )["decisions"]
            self.assertEqual("metadata-only-json", decisions[0]["selection_reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)