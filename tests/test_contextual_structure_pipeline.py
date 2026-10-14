"""Tests for section-aware batched Stage 3 discovery."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.contextual_structure_pipeline import (  # noqa: E402
    ContextualStructureDiscoveryPipeline, _segment_hash,
)
from mirrulations_markdown.pipeline import STAGE_2  # noqa: E402
from mirrulations_markdown.structure_models import (  # noqa: E402
    BackwardReference, ModelSpec, SegmentBlockEnrichment, SegmentEnrichment,
    StructureConfiguration,
)


class ContextualStructurePipelineTest(unittest.TestCase):
    def test_regulatory_documents_are_processed_before_comments(self):
        calls = []

        async def caller(**kwargs):
            calls.append(kwargs["document_type"])
            return SegmentEnrichment(
                section_summary=None,
                block_results=[
                    SegmentBlockEnrichment(block_id=kwargs["owned_block_ids"][0])
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            markdown_db = Path(directory) / "markdown"
            for name, source_key, role, reason in (
                ("comment", "a-comment.json", "form_comment", "comment"),
                ("rule", "z-rule.html", "regulatory_document", "regulation"),
            ):
                asset = {
                    "source_object_key": source_key, "source_sha256": name,
                    "markdown_path": f"{name}.md", "selection_reason": reason,
                }
                block_root = markdown_db / "metadata/blocks"
                block_root.mkdir(parents=True, exist_ok=True)
                block_root.joinpath(f"{name}.json").write_text(json.dumps({
                    "asset": asset,
                    "document_metadata": {"logical_document_role": role},
                    "blocks": [{
                        "block_id": "paragraph-0001", "block_type": "paragraph",
                        "order": 1, "plain_text": "Substantive text.",
                    }],
                    "target_registry": [],
                }))
                stage_2 = markdown_db / STAGE_2 / asset["markdown_path"]
                stage_2.parent.mkdir(parents=True, exist_ok=True)
                stage_2.write_text("source")
            model = ModelSpec(provider="openai", model="test")
            ContextualStructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db,
                configuration=StructureConfiguration(
                    summary_model=model, reference_model=model,
                ),
                segment_caller=caller,
            )
            self.assertEqual(["regulation", "comment"], calls)

    def test_segment_hash_changes_with_target_semantics(self):
        common = {
            "source_hash": "source", "segment": {"segment_id": "one"},
            "configuration_hash": "configuration",
        }
        first = _segment_hash(
            **common, target_registry=[{
                "target_key": "document:ONE", "relationship_type": "direct_comment_on",
            }]
        )
        second = _segment_hash(
            **common, target_registry=[{
                "target_key": "document:ONE", "relationship_type": "supports",
            }]
        )
        self.assertNotEqual(first, second)

    def test_analyzes_section_and_whole_list_in_one_call(self):
        calls = []

        async def caller(**kwargs):
            calls.append(kwargs)
            return SegmentEnrichment(
                section_summary="The section recommends shorter decision timeframes.",
                block_results=[
                    SegmentBlockEnrichment(block_id="paragraph-0001"),
                    SegmentBlockEnrichment(
                        block_id="list-0001",
                        backward_references=[BackwardReference(
                            target_key="document:TARGET-1",
                            search_description="the seven-day standard decision timeframe",
                        )],
                    ),
                    SegmentBlockEnrichment(block_id="paragraph-0002"),
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            markdown_db = Path(directory) / "markdown"
            asset = {
                "source_object_key": "raw-data/CMS/docket/comments/COMMENT-1.json",
                "source_sha256": "hash", "markdown_path": "comments/COMMENT-1.md",
                "selection_reason": "form-submitted-comment-body",
            }
            blocks = [
                {"block_id": "section-0001", "block_type": "section", "order": 1,
                 "plain_text": "I. Timing", "heading_context": []},
                {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 2,
                 "plain_text": "The current standard is too slow.", "heading_context": []},
                {"block_id": "list-0001", "block_type": "list", "order": 3,
                 "plain_text": "- Use 24 hours\n- Use 48 hours", "items": ["Use 24 hours", "Use 48 hours"], "heading_context": []},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 4,
                 "plain_text": "These changes prevent harm.", "heading_context": []},
            ]
            block_root = markdown_db / "metadata/blocks"
            block_root.mkdir(parents=True)
            (block_root / "source.json").write_text(json.dumps({
                "asset": asset, "alignment": None, "blocks": blocks,
                "target_registry": [{
                    "target_key": "document:TARGET-1", "document_ids": ["TARGET-1"],
                    "scope_label": "this proposed rule TEST-P",
                }],
            }))
            stage_2 = markdown_db / STAGE_2 / asset["markdown_path"]
            stage_2.parent.mkdir(parents=True)
            stage_2.write_text(
                '<a id="section-0001"></a>\n\n## I. Timing\n\n'
                '<a id="paragraph-0001"></a>\n\nThe current standard is too slow.\n\n'
                '<a id="list-0001"></a>\n\n- Use 24 hours\n- Use 48 hours\n\n'
                '<a id="paragraph-0002"></a>\n\nThese changes prevent harm.\n'
            )
            model = ModelSpec(provider="openai", model="test")
            result = ContextualStructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db,
                configuration=StructureConfiguration(
                    summary_model=model, reference_model=model,
                    summary_prompt_version=1, reference_prompt_version=1,
                ),
                segment_caller=caller,
            )
            self.assertEqual(1, result["api_calls"])
            self.assertEqual(1, len(calls))
            self.assertEqual(
                ["paragraph-0001", "list-0001", "paragraph-0002"],
                calls[0]["owned_block_ids"],
            )
            sidecar = json.loads(
                (markdown_db / "metadata/structure_discovery/annotations/source.json").read_text()
            )
            list_annotation = next(
                item for item in sidecar["annotations"] if item["block_id"] == "list-0001"
            )
            self.assertEqual(
                "list-0001",
                list_annotation["backward_references"][0]["source_block_id"],
            )

    def test_rejects_missing_owned_block_result(self):
        async def caller(**_kwargs):
            return SegmentEnrichment(
                section_summary=None,
                block_results=[SegmentBlockEnrichment(block_id="paragraph-0001")],
            )
        # Exact response validation is exercised through the worker helper.
        from mirrulations_markdown.contextual_structure_pipeline import _call_segment
        model = ModelSpec(provider="openai", model="test")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            _call_segment(
                caller=caller,
                configuration=StructureConfiguration(
                    summary_model=model, reference_model=model,
                ),
                asset={"source_sha256": "hash"},
                segment={
                    "section_heading": None, "section_block_id": None,
                    "owned_block_ids": ["paragraph-0001", "paragraph-0002"],
                    "blocks": [],
                },
                target_registry=[], allowed_targets_by_key={}, segment_hash="hash",
            )

    def test_failed_document_does_not_overwrite_existing_sidecar(self):
        async def failing_caller(**_kwargs):
            raise RuntimeError("provider unavailable")

        with tempfile.TemporaryDirectory() as directory:
            markdown_db = Path(directory) / "markdown"
            asset = {
                "source_object_key": "comments/COMMENT-1.json",
                "source_sha256": "hash", "markdown_path": "comments/COMMENT-1.md",
                "selection_reason": "form-submitted-comment-body",
            }
            block_root = markdown_db / "metadata/blocks"
            block_root.mkdir(parents=True)
            (block_root / "source.json").write_text(json.dumps({
                "asset": asset, "alignment": None,
                "document_metadata": {"logical_document_role": "form_comment"},
                "blocks": [{
                    "block_id": "paragraph-0001", "block_type": "paragraph",
                    "order": 1, "plain_text": "The deadline is too short.",
                }],
                "target_registry": [{
                    "target_key": "document:TARGET-1", "scope_label": "test target",
                }],
            }))
            stage_2 = markdown_db / STAGE_2 / asset["markdown_path"]
            stage_2.parent.mkdir(parents=True)
            stage_2.write_text("source")
            sidecar = markdown_db / "metadata/structure_discovery/annotations/source.json"
            sidecar.parent.mkdir(parents=True)
            original = {"schema_version": 2, "annotations": [{"block_id": "old"}]}
            sidecar.write_text(json.dumps(original))
            model = ModelSpec(provider="openai", model="test")
            result = ContextualStructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db,
                configuration=StructureConfiguration(
                    summary_model=model, reference_model=model,
                ),
                segment_caller=failing_caller,
            )
            self.assertEqual(1, result["failed_task_count"])
            self.assertEqual(1, result["completed_documents"])
            written = json.loads(sidecar.read_text())
            problematic = [
                item for item in written["annotations"]
                if item.get("task_status") == "problematic"
            ]
            self.assertEqual(1, len(problematic))
            self.assertEqual("paragraph-0001", problematic[0]["block_id"])
            self.assertIn("RuntimeError", problematic[0]["error"])

            budget_result = ContextualStructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db,
                configuration=StructureConfiguration(
                    summary_model=model, reference_model=model,
                ),
                segment_caller=failing_caller,
                maximum_api_calls=0,
            )
            self.assertEqual(1, budget_result["failed_task_count"])
            self.assertIn("budget exhausted", budget_result["failed_tasks"][0]["error"])
            self.assertEqual(1, budget_result["completed_documents"])


if __name__ == "__main__":
    unittest.main(verbosity=2)