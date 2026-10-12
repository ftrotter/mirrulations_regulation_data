"""Tests for isolated cross-provider Stage 4 runs and checkpoints."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.full_context_linker import (  # noqa: E402
    FullContextLinkBatch, FullContextLinkResult, RelationshipEvidence,
)
from mirrulations_markdown.premium_linker import (  # noqa: E402
    OpenAICachedContextAdapter, PremiumReferenceLinkerPipeline,
)
from mirrulations_markdown.reference_linker import STAGE_3  # noqa: E402


class FakePremiumAdapter:
    provider = "anthropic"
    model = "test-model"

    def __init__(self, *, fail_call=None):
        self.calls = 0
        self.fail_call = fail_call

    def prepare_target_context(self, *, target_context):
        return {"cache_strategy": "test", "context": target_context["context_sha256"]}

    async def submit_question_batch(self, *, prepared_context, questions):
        self.calls += 1
        if self.calls == self.fail_call:
            raise RuntimeError("synthetic provider failure")
        return {
            "batch": FullContextLinkBatch(results=[FullContextLinkResult(
                reference_id=question["reference_id"],
                primary_relationship_class="other_substantive_relationship",
                match_status="linked", primary_target_ids=["paragraph-0002"],
                confidence=0.9,
                relationship_evidence=RelationshipEvidence(
                    comment_position="The deadline is too long.",
                    agency_position="The agency proposes seven days.",
                    link_explanation="The comment opposes the deadline.",
                ),
            ) for question in questions]),
            "latency_seconds": 0.1,
            "usage": {"cache_read_input_tokens": 100, "total_tokens": 120},
            "response_id": f"response-{self.calls}", "model_version": self.model,
        }

    def release_target_context(self, *, prepared_context):
        return None


class PremiumLinkerTest(unittest.TestCase):
    def test_openai_cache_key_respects_provider_limit(self):
        adapter = object.__new__(OpenAICachedContextAdapter)
        prepared = adapter.prepare_target_context(target_context={
            "context_sha256": "a" * 64,
            "serialized_context": "target",
        })
        self.assertLessEqual(len(prepared["prompt_cache_key"]), 64)

    def test_existing_checkpoints_are_scoped_to_requested_work(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = self._write_corpus(root_path=Path(directory))
            first = PremiumReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, provider="anthropic", model="test-model",
                adapter=FakePremiumAdapter(), batch_size=2, maximum_concurrency=1,
            )
            self.assertEqual(2, first["references_completed"])
            source_key = "raw-data/CMS/docket/comments/COMMENT-1.json"
            second = PremiumReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, provider="anthropic", model="test-model",
                adapter=FakePremiumAdapter(), source_object_keys=[source_key],
            )
            self.assertEqual(2, second["references_requested"])
            self.assertEqual(2, second["references_reused"])

    @staticmethod
    def _write_corpus(*, root_path):
        markdown_db = root_path / "markdown"
        block_root = markdown_db / "metadata/blocks"
        annotation_root = markdown_db / "metadata/structure_discovery/annotations"
        block_root.mkdir(parents=True)
        annotation_root.mkdir(parents=True)
        source_key = "raw-data/CMS/docket/comments/COMMENT-1.json"
        source_asset = {"source_object_key": source_key, "source_sha256": "hash",
                        "markdown_path": "comments/COMMENT-1.md"}
        name = __import__("hashlib").sha256(source_key.encode()).hexdigest()
        source_blocks = [
            {"block_id": f"paragraph-{index:04d}", "block_type": "paragraph",
             "order": index, "plain_text": f"Deadline comment {index}."}
            for index in (1, 3)
        ]
        (block_root / f"{name}.json").write_text(json.dumps({
            "asset": source_asset, "blocks": source_blocks,
        }))
        (block_root / "target.json").write_text(json.dumps({
            "asset": {"source_object_key": "raw-data/CMS/docket/documents/TARGET-1.html",
                      "markdown_path": "documents/TARGET-1.md"},
            "blocks": [{"block_id": "paragraph-0002", "block_type": "paragraph",
                        "order": 1, "plain_text": "We propose seven days."}],
        }))
        (annotation_root / f"{name}.json").write_text(json.dumps({
            "asset": source_asset,
            "annotations": [{"backward_references": [{
                "source_block_id": block["block_id"], "target_key": "document:TARGET-1",
                "search_description": f"deadline {index}",
                "target": {"document_ids": ["TARGET-1"]},
            } for index, block in enumerate(source_blocks, start=1)]}],
        }))
        stage_3_path = markdown_db / STAGE_3 / source_asset["markdown_path"]
        stage_3_path.parent.mkdir(parents=True)
        stage_3_path.write_text("stage 3")
        return markdown_db

    def test_persists_successful_batch_before_later_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = self._write_corpus(root_path=Path(directory))
            failing_adapter = FakePremiumAdapter(fail_call=2)
            first = PremiumReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, provider="anthropic", model="test-model",
                adapter=failing_adapter, batch_size=1, maximum_concurrency=1,
                retry_count=0,
            )
            self.assertEqual(1, first["references_completed"])
            self.assertEqual(1, first["failed_batch_count"])
            checkpoints = list((markdown_db / "metadata/reference_link_benchmarks").rglob(
                "batch-*.json"
            ))
            self.assertEqual(1, len(checkpoints))

            recovery_adapter = FakePremiumAdapter()
            second = PremiumReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db, provider="anthropic", model="test-model",
                adapter=recovery_adapter, batch_size=1, maximum_concurrency=1,
            )
            self.assertEqual(2, second["references_completed"])
            self.assertEqual(1, second["references_reused"])
            self.assertEqual(1, recovery_adapter.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)