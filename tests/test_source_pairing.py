"""Tests for canonical extraction and original attachment pairing."""

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.source_pairing import (  # noqa: E402
    extracted_attachment_identity,
    pair_extracted_attachments,
)


class SourcePairingTest(unittest.TestCase):
    def test_parses_extracted_attachment_identity(self):
        self.assertEqual(
            ("CMS-2026-1255-0002", 1),
            extracted_attachment_identity(
                file_name="CMS-2026-1255-0002_attachment_1_extracted.txt"
            ),
        )

    def test_prefers_single_matching_pdf(self):
        canonical_key = (
            "derived-data/CMS/docket/mirrulations/extracted_txt/"
            "comments_extracted_text/pypdf/"
            "CMS-2026-1255-0002_attachment_1_extracted.txt"
        )
        pdf_key = (
            "raw-data/CMS/docket/binary-docket/comments_attachments/"
            "CMS-2026-1255-0002_attachment_1.pdf"
        )
        assets = [
            {"source_object_key": canonical_key, "source_sha256": "text", "source_suffix": ".txt"},
            {"source_object_key": pdf_key, "source_sha256": "pdf", "source_suffix": ".pdf"},
        ]
        pairing = pair_extracted_attachments(
            source_root=Path("/unused"), assets=assets
        )[canonical_key]
        self.assertEqual("available-pdf", pairing["status"])
        self.assertEqual(pdf_key, pairing["structural_source_object_key"])

    def test_marks_docx_only_pair_pending(self):
        canonical_key = "derived/pypdf/TEST-1_attachment_2_extracted.txt"
        assets = [
            {"source_object_key": canonical_key, "source_sha256": "text", "source_suffix": ".txt"},
            {"source_object_key": "raw/TEST-1_attachment_2.docx", "source_sha256": "docx", "source_suffix": ".docx"},
        ]
        pairing = pair_extracted_attachments(
            source_root=Path("/unused"), assets=assets
        )[canonical_key]
        self.assertEqual("available-docx", pairing["status"])

    def test_prefers_docx_over_pdf(self):
        canonical_key = "derived/pypdf/TEST-1_attachment_2_extracted.txt"
        assets = [
            {"source_object_key": canonical_key, "source_sha256": "text", "source_suffix": ".txt"},
            {"source_object_key": "raw/TEST-1_attachment_2.docx", "source_sha256": "docx", "source_suffix": ".docx"},
            {"source_object_key": "raw/TEST-1_attachment_2.pdf", "source_sha256": "pdf", "source_suffix": ".pdf"},
        ]
        pairing = pair_extracted_attachments(
            source_root=Path("/unused"), assets=assets
        )[canonical_key]
        self.assertEqual("available-docx", pairing["status"])
        self.assertTrue(pairing["structural_source_object_key"].endswith(".docx"))
        self.assertEqual("pdf", pairing["alternate_structural_sources"][0]["format"])

    def test_ambiguous_pdfs_do_not_reuse_previous_selection(self):
        first_key = "derived-data/A/A-1/pypdf/A-1-0001_attachment_1_extracted.txt"
        second_key = "derived-data/A/A-1/pypdf/A-1-0002_attachment_1_extracted.txt"
        assets = [
            {"source_object_key": first_key, "source_sha256": "text-1", "source_suffix": ".txt"},
            {"source_object_key": "raw-data/A/A-1/files/A-1-0001_attachment_1.pdf",
             "source_sha256": "pdf-1", "source_suffix": ".pdf"},
            {"source_object_key": second_key, "source_sha256": "text-2", "source_suffix": ".txt"},
            {"source_object_key": "raw-data/A/A-1/one/A-1-0002_attachment_1.pdf",
             "source_sha256": "pdf-2a", "source_suffix": ".pdf"},
            {"source_object_key": "raw-data/A/A-1/two/A-1-0002_attachment_1.pdf",
             "source_sha256": "pdf-2b", "source_suffix": ".pdf"},
        ]
        pairings = pair_extracted_attachments(source_root=Path("/unused"), assets=assets)
        self.assertEqual("available-pdf", pairings[first_key]["status"])
        self.assertEqual("ambiguous-pdf", pairings[second_key]["status"])
        self.assertIsNone(pairings[second_key]["structural_source_object_key"])

    def test_missing_and_image_only_originals_have_no_selected_source(self):
        missing_key = "derived-data/A/A-1/pypdf/A-1-0003_attachment_1_extracted.txt"
        image_key = "derived-data/A/A-1/pypdf/A-1-0004_attachment_1_extracted.txt"
        assets = [
            {"source_object_key": missing_key, "source_sha256": "text-3", "source_suffix": ".txt"},
            {"source_object_key": image_key, "source_sha256": "text-4", "source_suffix": ".txt"},
            {"source_object_key": "raw-data/A/A-1/files/A-1-0004_attachment_1.png",
             "source_sha256": "png", "source_suffix": ".png"},
        ]
        pairings = pair_extracted_attachments(source_root=Path("/unused"), assets=assets)
        self.assertEqual("missing-original", pairings[missing_key]["status"])
        self.assertIsNone(pairings[missing_key]["structural_source_object_key"])
        self.assertEqual("structure-pending-image", pairings[image_key]["status"])
        self.assertIsNone(pairings[image_key]["structural_source_object_key"])

    def test_does_not_pair_same_record_id_across_dockets(self):
        canonical_key = "derived-data/A/A-1/pypdf/SHARED_attachment_1_extracted.txt"
        assets = [
            {"source_object_key": canonical_key, "source_sha256": "text", "source_suffix": ".txt"},
            {"source_object_key": "raw-data/A/A-2/files/SHARED_attachment_1.pdf",
             "source_sha256": "wrong", "source_suffix": ".pdf"},
        ]
        pairing = pair_extracted_attachments(
            source_root=Path("/unused"), assets=assets
        )[canonical_key]
        self.assertEqual("missing-original", pairing["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)