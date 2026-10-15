"""Tests for regulatory extraction and CorEx topic generation."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.topic_pipeline import (  # noqa: E402
    build_graph_bundle,
    extract_regulatory_issues,
    fit_corex_topics,
    load_corpus,
    render_topic_enriched_stage,
    run_topic_pipeline,
)


def _block_record(*, role, document_id, source_hash, blocks):
    return {
        "schema_version": 1,
        "asset": {
            "source_object_key": f"records/{document_id}.txt",
            "source_sha256": source_hash,
            "markdown_path": f"records/{document_id}.md",
        },
        "document_metadata": {
            "document_id": document_id,
            "docket_id": "TEST-2026-0001",
            "logical_document_role": role,
            "title": document_id,
        },
        "blocks": [
            {
                "block_id": f"{block_type}-{index:04d}",
                "block_type": block_type,
                "order": index,
                "plain_text": text,
                "heading_context": [],
                "parent_section_id": None,
            }
            for index, (block_type, text) in enumerate(blocks, 1)
        ],
    }


def _fixture(*, root):
    markdown_db = root / "markdown"
    block_root = markdown_db / "metadata" / "blocks"
    block_root.mkdir(parents=True)
    records = [
        _block_record(
            role="regulatory_document", document_id="TEST-2026-0001-0001",
            source_hash="a" * 64,
            blocks=[
                ("section", "Electronic Prior Authorization Implementation"),
                ("paragraph", "We propose electronic prior authorization requirements."),
            ],
        ),
        _block_record(
            role="form_comment", document_id="TEST-2026-0001-0002",
            source_hash="b" * 64,
            blocks=[
                ("paragraph", "Vendor implementation deadlines create readiness costs and delays."),
                ("paragraph", "Electronic prior authorization APIs need implementation support."),
            ],
        ),
        _block_record(
            role="comment_attachment", document_id="TEST-2026-0001-0003",
            source_hash="c" * 64,
            blocks=[
                ("paragraph", "Vendor implementation deadlines create readiness costs and delays."),
                ("paragraph", "Cybersecurity safeguards protect electronic patient information."),
            ],
        ),
    ]
    for index, record in enumerate(records):
        (block_root / f"{'d' * 63}{index}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
    return markdown_db


class TopicPipelineTest(unittest.TestCase):
    def test_rule_based_extraction_uses_section_evidence(self):
        document = {
            "blocks": [{
                "block_id": "section-0001", "block_type": "section",
                "plain_text": "Electronic Prior Authorization Implementation",
            }]
        }
        issues = extract_regulatory_issues(
            regulatory_document=document, mode="rule-based"
        )
        self.assertEqual(1, len(issues))
        self.assertEqual("section-0001", issues[0]["block_id"])

    def test_rule_based_extraction_consolidates_repeated_headings(self):
        document = {"blocks": [
            {
                "block_id": "section-0001", "block_type": "section",
                "plain_text": "Electronic Prior Authorization Implementation",
            },
            {
                "block_id": "section-0002", "block_type": "section",
                "plain_text": "Electronic Prior Authorization Implementation",
            },
        ]}
        issues = extract_regulatory_issues(
            regulatory_document=document, mode="rule-based"
        )
        self.assertEqual(1, len(issues))

    def test_langextract_requires_api_key(self):
        with self.assertRaisesRegex(ValueError, "requires LANGEXTRACT_API_KEY"):
            extract_regulatory_issues(
                regulatory_document={"blocks": []}, mode="langextract"
            )

    def test_langextract_adapter_maps_extractions_to_issues(self):
        class Extraction:
            extraction_class = "proposal"
            extraction_text = "require electronic prior authorization"
            attributes = {"topic": "electronic prior authorization"}

        class Result:
            extractions = [Extraction()]

        calls = []

        def extractor(**arguments):
            calls.append(arguments)
            return Result()

        document = {"blocks": [{
            "block_id": "paragraph-0001", "block_type": "paragraph",
            "plain_text": (
                "We propose to require electronic prior authorization for all "
                "covered drugs using the applicable implementation standard."
            ),
        }]}
        issues = extract_regulatory_issues(
            regulatory_document=document, mode="langextract", extractor=extractor,
            model_id="test-model",
        )
        self.assertEqual(1, len(calls))
        self.assertEqual("test-model", calls[0]["model_id"])
        self.assertEqual("langextract", issues[0]["extraction_method"])
        self.assertEqual("proposed", issues[0]["review_status"])

    def test_langextract_checkpoint_prevents_repeat_call(self):
        class Result:
            extractions = []

        calls = []

        def extractor(**arguments):
            calls.append(arguments)
            return Result()

        document = {"blocks": [{
            "block_id": "paragraph-0001", "block_type": "paragraph",
            "plain_text": (
                "We propose to require electronic prior authorization for all "
                "covered drugs using the applicable implementation standard."
            ),
        }]}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint_path = Path(directory) / "checkpoint.json"
            for _iteration in range(2):
                extract_regulatory_issues(
                    regulatory_document=document, mode="langextract",
                    extractor=extractor, checkpoint_path=checkpoint_path,
                )
        self.assertEqual(1, len(calls))

    def test_corex_tracks_exact_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = _fixture(root=Path(directory))
            corpus = load_corpus(
                markdown_db_path=markdown_db,
                browser_base_url="http://127.0.0.1:8765",
            )
            issues = extract_regulatory_issues(
                regulatory_document=corpus["regulatory_documents"][0],
                mode="rule-based",
            )
            result = fit_corex_topics(
                comments=corpus["comments"], agency_issues=issues,
                topic_count=2, random_seed=1, minimum_document_frequency=1,
                maximum_document_fraction=1, anchor_strength=2,
                assignment_threshold=0.5,
            )
            self.assertEqual(4, result["source_block_count"])
            self.assertEqual(1, result["exact_duplicate_count"])
            self.assertEqual(2, len(result["topics"]))
            assignments_by_block = {}
            for assignment in result["assignments"]:
                assignments_by_block.setdefault(assignment["block_key"], 0)
                assignments_by_block[assignment["block_key"]] += 1
            self.assertTrue(all(count <= 3 for count in assignments_by_block.values()))

    def test_topic_enriched_stage_preserves_stage_four_and_adds_topics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_db = _fixture(root=root)
            corpus = load_corpus(
                markdown_db_path=markdown_db,
                browser_base_url="http://127.0.0.1:8765",
            )
            document = corpus["comments"][0]
            source_path = (
                markdown_db / "stage004_backward_reference_links"
                / document["asset"]["markdown_path"]
            )
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                '<a id="paragraph-0001"></a>\n\nOriginal text.\n',
                encoding="utf-8",
            )
            topic_id = "topic-01JAB7Q4H1G25Z4NR2ME19JQYT"
            catalog_path = root / "topics.md"
            catalog_path.write_text("# Topics\n", encoding="utf-8")
            render_topic_enriched_stage(
                markdown_db_path=markdown_db, corpus=corpus,
                topics=[{"topic_id": topic_id, "label": "Vendor readiness"}],
                assignments=[{
                    "representation_id": document["representation_id"],
                    "block_id": "paragraph-0001", "topic_id": topic_id,
                    "score": 0.99,
                }],
                topic_catalog_path=catalog_path,
            )
            target_path = (
                markdown_db / "stage005_topic_enrichment"
                / document["asset"]["markdown_path"]
            )
            rendered = target_path.read_text(encoding="utf-8")
            self.assertIn("Original text.", rendered)
            self.assertIn("🏷️ **Topics:**", rendered)
            self.assertIn("Vendor readiness", rendered)

    def test_fixture_pipeline_writes_graph_and_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_db = _fixture(root=root)
            output_root = root / "output"
            result = run_topic_pipeline(
                markdown_db_path=markdown_db, output_root=output_root,
                browser_base_url="http://127.0.0.1:8765",
                extraction_mode="rule-based", topic_count=2, random_seed=1,
                minimum_document_frequency=1, maximum_document_fraction=1,
                anchor_strength=2, assignment_threshold=0.5,
            )
            self.assertGreater(result["node_count"], 0)
            for name in (
                "run.json", "topics.json", "topic_assignments.json",
                "topics.md", "initial-regulatory-issues.md", "topic-mapping.md",
                "graph_bundle.json",
            ):
                self.assertTrue((output_root / name).is_file(), name)

            graph_bundle = json.loads(
                (output_root / "graph_bundle.json").read_text(encoding="utf-8")
            )
            overview_relationships = [
                relationship for relationship in graph_bundle["relationships"]
                if relationship["relationship_type"] == "DISCUSSES_TOPIC"
            ]
            self.assertTrue(overview_relationships)
            self.assertTrue(all(
                relationship["source_label"] == "Document"
                and relationship["target_label"] == "Topic"
                and relationship["properties"]["matched_block_count"] >= 1
                and relationship["properties"]["maximum_score"] >= 0.5
                for relationship in overview_relationships
            ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
