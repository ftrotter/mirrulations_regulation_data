"""Tests for citation adapters, reconciliation, and safe rendering."""

from pathlib import Path
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.citations import (  # noqa: E402
    extract_eyecite_citations,
    reconcile_candidates,
)


class EyeciteAdapterTest(unittest.TestCase):
    def test_extracts_case_with_unicode_code_point_offsets(self):
        text = "É agency cites Foo v. Bar, 123 F.3d 456, 460 (9th Cir. 2001)."
        candidates, status = extract_eyecite_citations(
            text=text, document_version="version", block_id="p-0001"
        )
        self.assertEqual("success", status["status"])
        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual(candidate["matched_text"], text[candidate["start"] : candidate["end"]])
        self.assertEqual("case", candidate["citation_family"])
        self.assertEqual("FullCaseCitation", candidate["structured_components"]["citation_class"])

    def test_success_with_zero_findings_is_not_failure(self):
        candidates, status = extract_eyecite_citations(
            text="No legal authority here.",
            document_version="version",
            block_id="p-0001",
        )
        self.assertEqual([], candidates)
        self.assertEqual("success", status["status"])
        self.assertEqual(0, status["finding_count"])

    def test_normalizes_usc_to_provider_independent_target(self):
        candidates, status = extract_eyecite_citations(
            text="The agency acted under 5 U.S.C. § 553.",
            document_version="version",
            block_id="p-0001",
        )
        self.assertEqual("success", status["status"])
        self.assertEqual("usc:5:553", candidates[0]["normalized_target"])

    @mock.patch("eyecite.get_citations", side_effect=RuntimeError("broken tokenizer"))
    def test_library_failure_is_reported_independently(self, _get_citations):
        candidates, status = extract_eyecite_citations(
            text="1 U.S. 2", document_version="version", block_id="p-0001"
        )
        self.assertEqual([], candidates)
        self.assertEqual("failed", status["status"])
        self.assertIn("broken tokenizer", status["detail"])


class ReconciliationTest(unittest.TestCase):
    def test_merges_same_occurrence_and_target_with_adapter_provenance(self):
        base = {
            "block_id": "p-0001",
            "start": 0,
            "end": 10,
            "normalized_target": "usc:5:553",
            "warnings": [],
        }
        reconciled = reconcile_candidates(
            candidates=[
                {**base, "adapter_name": "first"},
                {**base, "adapter_name": "second"},
            ]
        )
        self.assertEqual(1, len(reconciled))
        self.assertEqual(["first", "second"], reconciled[0]["supporting_adapters"])

    def test_flags_competing_overlaps(self):
        candidates = [
            {
                "block_id": "p-0001", "start": 0, "end": 10,
                "normalized_target": "one", "warnings": [], "adapter_name": "a",
            },
            {
                "block_id": "p-0001", "start": 5, "end": 12,
                "normalized_target": "two", "warnings": [], "adapter_name": "b",
            },
        ]
        reconciled = reconcile_candidates(candidates=candidates)
        self.assertTrue(
            all("overlap_competing_finding" in item["warnings"] for item in reconciled)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)