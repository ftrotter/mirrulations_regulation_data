"""Tests for Regulations.gov lifecycle metadata research."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.regulations_gov_research import (  # noqa: E402
    ArtifactCategory, RegulationsGovClient, RegulationsGovResearch, _matches,
)


class RegulationsGovResearchTest(unittest.TestCase):
    def test_category_match_uses_metadata_and_title(self):
        category = ArtifactCategory(
            "anprm", "ANPRM", "ANPRM", document_types=("Proposed Rule",),
            subtypes=("Advance Notice of Proposed Rulemaking (ANPRM)",),
            title_terms=("advance notice of proposed rulemaking",),
        )
        document = {"attributes": {
            "documentType": "Proposed Rule",
            "subtype": "Advance Notice of Proposed Rulemaking (ANPRM)",
            "title": "Advance Notice of Proposed Rulemaking for Test Program",
        }}
        self.assertTrue(_matches(category=category, document=document))
        document["attributes"]["documentType"] = "Supporting & Related Material"
        self.assertFalse(_matches(category=category, document=document))

    def test_title_terms_are_alternatives(self):
        category = ArtifactCategory(
            "meeting", "Meeting", "Meeting",
            title_terms=("public meeting", "public hearing", "listening session"),
        )
        self.assertTrue(_matches(
            category=category,
            document={"attributes": {"title": "Notice of a Public Hearing"}},
        ))

    def test_client_reuses_pretty_printed_cache(self):
        payload = {"data": [{"id": "TEST-1"}]}
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "mirrulations_markdown.regulations_gov_research.urlopen",
                return_value=response,
            ) as mocked_urlopen, patch(
                "mirrulations_markdown.regulations_gov_research.json.load",
                return_value=payload,
            ):
                client = RegulationsGovClient(
                    api_key="secret", cache_root=Path(directory), requests_per_second=1000,
                )
                first = client.get(resource_path="documents", parameters={"page[size]": 5})
                second = client.get(resource_path="documents", parameters={"page[size]": 5})
            self.assertEqual(payload, first)
            self.assertEqual(payload, second)
            self.assertEqual(1, mocked_urlopen.call_count)
            cached = next(Path(directory).glob("*.json"))
            self.assertEqual(payload, json.loads(cached.read_text()))
            self.assertIn("\n  ", cached.read_text())

    def test_candidate_search_applies_exact_metadata_filters(self):
        category = ArtifactCategory(
            "sorn", "SORN", "System of Records", document_types=("Notice",),
            subtypes=("System of Records",),
        )
        client = unittest.mock.MagicMock()
        client.get.return_value = {"data": [], "meta": {"lastPage": True}}
        RegulationsGovResearch._candidate_search(
            client=client, category=category, search_size=25, minimum_matches=5,
        )
        parameters = client.get.call_args.kwargs["parameters"]
        self.assertEqual("Notice", parameters["filter[documentType]"])
        self.assertEqual("System of Records", parameters["filter[subtype]"])

    def test_public_comment_search_uses_document_object_id(self):
        document = {
            "id": "AGENCY-2026-0001-0001",
            "attributes": {"objectId": "0900000000000001"},
        }
        self.assertNotEqual(document["id"], document["attributes"]["objectId"])

    def test_summary_retains_join_identifiers(self):
        manifest = {
            "research_version": 1, "generated_at": "2026-01-01T00:00:00Z",
            "api_root": "https://example.test", "evidence": [{
                "category_key": "nprm", "category_label": "NPRM",
                "accepted_sample_size": 1, "examples": [{
                    "document": {"id": "A-1", "attributes": {
                        "docketId": "A", "objectId": "opaque", "documentType": "Proposed Rule",
                    }},
                    "docket": {"id": "A", "attributes": {"docketType": "Rulemaking", "rin": "0000-AA00"}},
                    "comment_search_object_id": "opaque", "comment_total": 1,
                    "comments": [{"id": "A-2"}],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            summary = RegulationsGovResearch.write_summary(
                output_root=Path(directory), manifest=manifest,
            )
        example = summary["categories"][0]["examples"][0]
        self.assertEqual("opaque", example["comment_search_object_id"])
        self.assertEqual(["A-2"], example["sample_comment_ids"])

    def test_export_examples_deduplicates_resources(self):
        document = {"id": "A-1", "attributes": {}}
        docket = {"id": "A", "attributes": {}}
        comment = {"id": "A-2", "attributes": {}}
        manifest = {
            "api_root": "https://example.test", "generated_at": "test",
            "evidence": [{
                "category_key": "one", "category_label": "One",
                "examples": [
                    {"document": document, "docket": docket, "comments": [comment]},
                    {"document": document, "docket": docket, "comments": [comment]},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = RegulationsGovResearch.export_examples(
                manifest=manifest, output_root=Path(directory),
            )
            file_count = len(list(Path(directory).rglob("*.json")))
        self.assertEqual(
            {"documents": 1, "dockets": 1, "comments": 1},
            result["unique_resource_counts"],
        )
        self.assertEqual(4, file_count)


if __name__ == "__main__":
    unittest.main(verbosity=2)