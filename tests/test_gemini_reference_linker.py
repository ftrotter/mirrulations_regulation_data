"""Tests for the Gemini full-context Stage 4 pipeline."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.full_context_linker import (  # noqa: E402
    FullContextLinkBatch, FullContextLinkResult, RelationshipEvidence,
)
from mirrulations_markdown.gemini_reference_linker import (  # noqa: E402
    GeminiReferenceLinkerPipeline, _gemini_response_schema,
)
from mirrulations_markdown.reference_linker import STAGE_3, STAGE_4  # noqa: E402


class FakeGeminiAdapter:
    def __init__(self):
        self.prepared = 0
        self.released = 0
        self.calls = 0

    def prepare_target_context(self, *, target_context):
        self.prepared += 1
        self.target_context = target_context
        return {"cache_name": "cachedContents/test", "cached_content_token_count": 100}

    async def submit_question_batch(self, *, prepared_context, questions):
        self.calls += 1
        self.assert_cache_name = prepared_context["cache_name"]
        results = [FullContextLinkResult(
            reference_id=question["reference_id"],
            primary_relationship_class="other_substantive_relationship",
            match_status="linked",
            primary_target_ids=["paragraph-0002"],
            confidence=0.95,
            relationship_evidence=RelationshipEvidence(
                comment_position="The deadline is too long.",
                agency_position="The agency proposes a seven-day deadline.",
                link_explanation="The comment opposes the proposed deadline.",
            ),
        ) for question in questions]
        return {
            "batch": FullContextLinkBatch(results=results),
            "latency_seconds": 0.1,
            "usage": {"cached_content_token_count": 100, "total_token_count": 120},
            "response_id": "response-1", "model_version": "test-model",
        }

    def release_target_context(self, *, prepared_context):
        self.released += 1


class GeminiReferenceLinkerTest(unittest.TestCase):
    def test_gemini_schema_omits_unsupported_additional_properties(self):
        schema = _gemini_response_schema(model_class=FullContextLinkBatch)
        self.assertNotIn("additionalProperties", json.dumps(schema))
        self.assertIn("results", schema["properties"])

    @staticmethod
    def _write_corpus(*, root_path):
        markdown_db = root_path / "markdown"
        block_root = markdown_db / "metadata" / "blocks"
        annotation_root = markdown_db / "metadata" / "structure_discovery" / "annotations"
        block_root.mkdir(parents=True)
        annotation_root.mkdir(parents=True)
        source_key = "raw-data/CMS/docket/comments/COMMENT-1.json"
        source_asset = {
            "source_object_key": source_key, "source_sha256": "source-hash",
            "markdown_path": "comments/COMMENT-1.md",
        }
        target_asset = {
            "source_object_key": "raw-data/CMS/docket/documents/TARGET-1_content.html",
            "source_sha256": "target-hash", "markdown_path": "documents/TARGET-1.md",
        }
        metadata_name = __import__("hashlib").sha256(source_key.encode()).hexdigest()
        (block_root / f"{metadata_name}.json").write_text(json.dumps({
            "asset": source_asset,
            "blocks": [{"block_id": "paragraph-0001", "block_type": "paragraph",
                        "order": 1, "plain_text": "The seven-day deadline is too long."}],
        }))
        (block_root / "target.json").write_text(json.dumps({
            "asset": target_asset,
            "blocks": [
                {"block_id": "section-0001", "block_type": "section", "order": 1,
                 "plain_text": "Decision timeframes"},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 2,
                 "plain_text": "We propose seven calendar days for standard decisions."},
            ],
        }))
        (annotation_root / f"{metadata_name}.json").write_text(json.dumps({
            "asset": source_asset,
            "annotations": [{"backward_references": [{
                "source_block_id": "paragraph-0001",
                "target_key": "document:TARGET-1",
                "search_description": "seven-calendar-day standard decision deadline",
                "target": {"document_ids": ["TARGET-1"]},
            }]}],
        }))
        stage_3_path = markdown_db / STAGE_3 / source_asset["markdown_path"]
        stage_3_path.parent.mkdir(parents=True)
        stage_3_path.write_text(
            '<a id="paragraph-0001"></a>\n\nThe seven-day deadline is too long.\n'
        )
        return markdown_db, source_key, metadata_name

    def test_builds_stage_4_and_reuses_rich_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db, source_key, metadata_name = self._write_corpus(
                root_path=Path(directory)
            )
            adapter = FakeGeminiAdapter()
            first = GeminiReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, model="test-model", adapter=adapter,
                batch_size=10, maximum_concurrency=1,
            )
            self.assertEqual(1, first["references_completed"])
            self.assertEqual(1, adapter.prepared)
            self.assertEqual(1, adapter.released)
            sidecar = json.loads(
                (markdown_db / "metadata/reference_links" / f"{metadata_name}.json").read_text()
            )
            self.assertEqual("other_substantive_relationship",
                             sidecar["links"][0]["relationship"]["primary_relationship_class"])
            output = (markdown_db / STAGE_4 / "comments/COMMENT-1.md").read_text()
            self.assertIn("#paragraph-0002", output)

            second = GeminiReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, model="test-model", adapter=adapter,
                source_object_keys=[source_key],
            )
            self.assertEqual(1, second["references_reused"])
            self.assertEqual(1, adapter.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)