"""Tests for the file-backed MVP graph and local Neo4j projection."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.graph_browser_links import comment_browser_url  # noqa: E402
from mirrulations_markdown.graph_io import (  # noqa: E402
    import_graph_bundle,
    load_graph_bundle,
    write_graph_bundle,
)
from mirrulations_markdown.graph_models import (  # noqa: E402
    EvidenceReference,
    GraphBundle,
    GraphNode,
    GraphRelationship,
    TopicAssignmentRecord,
    TopicRecord,
)


TOPIC_ID = "topic-01JAB7Q4H1G25Z4NR2ME19JQYT"
PARENT_TOPIC_ID = "topic-01JAB6XRVH4BHN0K6PBGJHP2VZ"
RUN_ID = "run-01JAB900000000000000000000"


def _bundle():
    return GraphBundle(
        generated_by_run_id=RUN_ID,
        nodes=[
            GraphNode(
                label="Block", stable_id="version-1:paragraph-0007",
                properties={
                    "comment_id": "CMS-2026-1255-0042",
                    "representation_id": "a" * 64,
                    "stage_number": 4,
                    "block_id": "paragraph-0007",
                },
            ),
            GraphNode(
                label="Topic", stable_id=TOPIC_ID,
                properties={"label": "Vendor readiness"},
            ),
        ],
        relationships=[
            GraphRelationship(
                relationship_type="ASSIGNED_TOPIC",
                source_label="Block", source_id="version-1:paragraph-0007",
                target_label="Topic", target_id=TOPIC_ID,
                properties={"assignment_id": "topic-assignment-" + "b" * 64},
            )
        ],
    )


class _FakeSession:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def run(self, query, **parameters):
        self.calls.append((query, parameters))


class _FakeDriver:
    def __init__(self):
        self.fake_session = _FakeSession()

    def session(self):
        return self.fake_session


class GraphDataTest(unittest.TestCase):
    def test_topic_rejects_self_parent(self):
        with self.assertRaisesRegex(ValueError, "own parent"):
            TopicRecord(
                topic_id=TOPIC_ID, label="Vendor readiness",
                description="Vendor implementation readiness.",
                origin="comment-derived", review_status="accepted",
                parent_topic_ids=[TOPIC_ID],
            )

    def test_evidence_requires_ordered_offsets(self):
        with self.assertRaisesRegex(ValueError, "greater than start"):
            EvidenceReference(
                document_version_id="version-1", block_id="paragraph-0007",
                start=10, end=2, matched_text="text",
            )

    def test_reviewed_assignment_requires_review_metadata(self):
        with self.assertRaisesRegex(ValueError, "require reviewer"):
            TopicAssignmentRecord(
                assignment_id="topic-assignment-" + "b" * 64,
                document_version_id="version-1", block_id="paragraph-0007",
                topic_id=TOPIC_ID, assignment_method="corex",
                analysis_run_id=RUN_ID, score=0.82, review_status="accepted",
            )
        assignment = TopicAssignmentRecord(
            assignment_id="topic-assignment-" + "b" * 64,
            document_version_id="version-1", block_id="paragraph-0007",
            topic_id=TOPIC_ID, assignment_method="corex",
            analysis_run_id=RUN_ID, score=0.82, review_status="accepted",
            reviewer="reviewer", reviewed_at=datetime.now(timezone.utc),
            review_rationale="The block directly discusses vendor readiness.",
        )
        self.assertEqual("accepted", assignment.review_status)

    def test_bundle_rejects_missing_relationship_endpoint(self):
        with self.assertRaisesRegex(ValueError, "endpoint does not exist"):
            GraphBundle(
                generated_by_run_id=RUN_ID,
                nodes=[GraphNode(label="Topic", stable_id=TOPIC_ID)],
                relationships=[GraphRelationship(
                    relationship_type="CHILD_OF",
                    source_label="Topic", source_id=TOPIC_ID,
                    target_label="Topic", target_id=PARENT_TOPIC_ID,
                )],
            )

    def test_bundle_round_trip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.json"
            second_path = Path(directory) / "second.json"
            write_graph_bundle(bundle=_bundle(), bundle_path=first_path)
            loaded_bundle = load_graph_bundle(bundle_path=first_path)
            write_graph_bundle(bundle=loaded_bundle, bundle_path=second_path)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(1, json.loads(first_path.read_text())["schema_version"])

    def test_import_creates_constraints_and_parameterized_merges(self):
        driver = _FakeDriver()
        import_graph_bundle(bundle=_bundle(), driver=driver)
        calls = driver.fake_session.calls
        self.assertEqual(5, len(calls))
        self.assertIn("CREATE CONSTRAINT IF NOT EXISTS", calls[0][0])
        self.assertTrue(any("UNWIND $rows" in query for query, _ in calls))
        self.assertTrue(any("MERGE (graph_node:Block" in query for query, _ in calls))
        self.assertTrue(any("ASSIGNED_TOPIC" in query for query, _ in calls))
        assignment_call = next(call for call in calls if "ASSIGNED_TOPIC" in call[0])
        self.assertEqual(TOPIC_ID, assignment_call[1]["rows"][0]["target_id"])

    def test_comment_browser_url_targets_stage_block(self):
        self.assertEqual(
            "http://127.0.0.1:8765/comments/CMS-2026-1255-0042/"
            f"representations/{'a' * 64}/stage/4/#paragraph-0007",
            comment_browser_url(
                browser_base_url="http://127.0.0.1:8765/",
                comment_id="CMS-2026-1255-0042", representation_id="a" * 64,
                stage_number=4, block_id="paragraph-0007",
            ),
        )

    def test_comment_browser_url_rejects_block_without_stage(self):
        with self.assertRaisesRegex(ValueError, "block_id requires stage_number"):
            comment_browser_url(
                browser_base_url="http://127.0.0.1:8765",
                comment_id="CMS-2026-1255-0042", block_id="paragraph-0007",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)