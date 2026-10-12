"""Tests for metadata-derived backward-reference target registries."""

from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.reference_targets import build_target_registry  # noqa: E402


class ReferenceTargetTest(unittest.TestCase):
    def test_real_comment_resolves_specific_proposed_rule(self):
        source_root = Path("data/source/mirrulations")
        targets = build_target_registry(
            source_root=source_root,
            source_object_key=(
                "raw-data/CMS/CMS-2026-1255/text-CMS-2026-1255/comments/"
                "CMS-2026-1255-0028.json"
            ),
        )
        self.assertEqual(1, len(targets))
        target = targets[0]
        self.assertEqual("document:CMS-2026-1255-0001", target["target_key"])
        self.assertEqual("CMS-0062-P", target["agency_rule_identifier"])
        self.assertEqual(
            "this proposed rule CMS-0062-P "
            "(Regulations.gov document CMS-2026-1255-0001)",
            target["scope_label"],
        )

    def test_attachment_inherits_parent_comment_target(self):
        source_root = Path("data/source/mirrulations")
        targets = build_target_registry(
            source_root=source_root,
            source_object_key=(
                "derived-data/CMS/CMS-2026-1255/mirrulations/extracted_txt/"
                "comments_extracted_text/pypdf/"
                "CMS-2026-1255-0273_attachment_1_extracted.txt"
            ),
        )
        self.assertEqual("document:CMS-2026-1255-0001", targets[0]["target_key"])

    def test_unrelated_non_json_document_has_no_invented_target(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                [],
                build_target_registry(
                    source_root=Path(directory), source_object_key="document.txt"
                ),
            )

    def test_sorn_comment_target_remains_a_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comment_path = root / "raw/D/D-1/comments/D-1-0002.json"
            document_path = root / "raw/D/D-1/documents/D-1-0001.json"
            comment_path.parent.mkdir(parents=True)
            document_path.parent.mkdir(parents=True)
            comment_path.write_text(json.dumps({"data": {
                "id": "D-1-0002", "type": "comments", "attributes": {
                    "docketId": "D-1", "commentOnDocumentId": "D-1-0001",
                },
            }}))
            document_path.write_text(json.dumps({"data": {
                "id": "D-1-0001", "type": "documents", "attributes": {
                    "docketId": "D-1", "documentType": "Notice",
                    "subtype": "System of Records", "title": "New System of Records",
                },
            }}))
            target = build_target_registry(
                source_root=root,
                source_object_key="raw/D/D-1/comments/D-1-0002.json",
            )[0]
        self.assertEqual("Notice", target["document_type"])
        self.assertEqual("System of Records", target["subtype"])
        self.assertEqual("direct_comment_on", target["relationship_type"])

    def test_rejects_comment_target_in_different_docket(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comment_path = root / "comments/C-1.json"
            document_path = root / "documents/D-1.json"
            comment_path.parent.mkdir()
            document_path.parent.mkdir()
            comment_path.write_text(json.dumps({"data": {
                "id": "C-1", "type": "comments", "attributes": {
                    "docketId": "DOCKET-A", "commentOnDocumentId": "D-1",
                },
            }}))
            document_path.write_text(json.dumps({"data": {
                "id": "D-1", "type": "documents", "attributes": {
                    "docketId": "DOCKET-B", "documentType": "Notice",
                },
            }}))
            with self.assertRaisesRegex(ValueError, "does not match"):
                build_target_registry(
                    source_root=root, source_object_key="comments/C-1.json",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)