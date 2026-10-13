"""Tests for exact regulatory-action block linking."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.reference_linker import (  # noqa: E402
    ReferenceLinkerPipeline, STAGE_3, STAGE_4, rank_target_blocks,
)
from mirrulations_markdown.structure_models import (  # noqa: E402
    ModelSpec, ReferenceLinkAssessment,
)


class ReferenceLinkerTest(unittest.TestCase):
    def test_ranks_specific_deadline_block_above_unrelated_block(self):
        ranked = rank_target_blocks(
            query_text="seven-calendar-day prior authorization decision timeframe",
            target_blocks=[
                {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
                 "plain_text": "We discuss general interoperability standards."},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 2,
                 "plain_text": "We propose a seven-calendar-day timeframe for standard prior authorization decisions."},
            ],
        )
        self.assertEqual("paragraph-0002", ranked[0]["block_id"])

    def test_query_description_is_not_diluted_by_source_comment_vocabulary(self):
        ranked = rank_target_blocks(
            query_text="72-hour expedited prior authorization determination timeframe",
            target_blocks=[
                {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
                 "plain_text": "ALS advocates discuss equipment and patient access."},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 2,
                 "plain_text": "Expedited prior authorization determinations must be made within 72 hours."},
            ],
        )
        self.assertEqual("paragraph-0002", ranked[0]["block_id"])

    def _corpus(self, *, root_path):
        markdown_db = root_path / "markdown"
        block_root = markdown_db / "metadata/blocks"
        annotation_root = markdown_db / "metadata/structure_discovery/annotations"
        block_root.mkdir(parents=True)
        annotation_root.mkdir(parents=True)
        source_asset = {
            "source_object_key": "raw-data/CMS/docket/comments/COMMENT-1.json",
            "source_sha256": "source-hash", "markdown_path": "comments/COMMENT-1.md",
        }
        target_asset = {
            "source_object_key": "raw-data/CMS/docket/documents/TARGET-1_content.html",
            "source_sha256": "target-hash", "markdown_path": "documents/TARGET-1.md",
        }
        source_record = {"asset": source_asset, "blocks": [{
            "block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
            "plain_text": "The seven-day deadline is too long.", "heading_context": [],
        }]}
        target_record = {"asset": target_asset, "blocks": [{
            "block_id": "paragraph-0002", "block_type": "paragraph", "order": 1,
            "plain_text": "We propose seven calendar days for standard decisions.",
            "heading_context": [],
        }]}
        (block_root / "source.json").write_text(json.dumps(source_record))
        (block_root / "target.json").write_text(json.dumps(target_record))
        annotation = {
            "asset": source_asset,
            "annotations": [{"backward_references": [{
                "source_block_id": "paragraph-0001", "target_key": "document:TARGET-1",
                "search_description": "seven-calendar-day standard decision timeframe",
                "target": {"document_ids": ["TARGET-1"]},
            }]}],
        }
        (annotation_root / "source.json").write_text(json.dumps(annotation))
        stage_3_path = markdown_db / STAGE_3 / source_asset["markdown_path"]
        stage_3_path.parent.mkdir(parents=True)
        stage_3_path.write_text(
            '<a id="paragraph-0001"></a>\n\nThe seven-day deadline is too long.\n'
        )
        return markdown_db

    def test_links_exact_candidate_and_reuses_sidecar(self):
        calls = []
        async def assessor(**kwargs):
            calls.append(kwargs)
            return ReferenceLinkAssessment(
                target_block_ids=["paragraph-0002"], confidence="high",
                rationale="The block states the exact decision timeframe.",
            )
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = self._corpus(root_path=Path(directory))
            arguments = {
                "markdown_db_path": markdown_db,
                "model_spec": ModelSpec(provider="openai", model="test"),
                "assessor": assessor,
            }
            first = ReferenceLinkerPipeline.run(**arguments)
            second = ReferenceLinkerPipeline.run(**arguments)
            self.assertEqual(1, first["api_calls"])
            self.assertEqual(0, second["api_calls"])
            self.assertEqual(1, len(calls))
            output = (markdown_db / STAGE_4 / "comments/COMMENT-1.md").read_text()
            self.assertIn("#paragraph-0002", output)

    def test_modified_after_filters_older_stage_three_sidecars(self):
        calls = []

        async def assessor(**_kwargs):
            calls.append(True)
            return ReferenceLinkAssessment(
                target_block_ids=[], confidence="no-match", rationale="No exact match."
            )

        with tempfile.TemporaryDirectory() as directory:
            markdown_db = self._corpus(root_path=Path(directory))
            future_cutoff = datetime.now(timezone.utc) + timedelta(minutes=1)
            result = ReferenceLinkerPipeline.run(
                markdown_db_path=markdown_db,
                model_spec=ModelSpec(provider="openai", model="test"),
                assessor=assessor,
                modified_after=future_cutoff,
            )
            self.assertEqual(0, result["completed_documents"])
            self.assertEqual([], calls)

    def test_rejects_invented_target_block(self):
        async def assessor(**_kwargs):
            return ReferenceLinkAssessment(
                target_block_ids=["paragraph-9999"], confidence="high",
                rationale="Invented block.",
            )
        with tempfile.TemporaryDirectory() as directory:
            result = ReferenceLinkerPipeline.run(
                markdown_db_path=self._corpus(root_path=Path(directory)),
                model_spec=ModelSpec(provider="openai", model="test"),
                assessor=assessor,
            )
            self.assertEqual(1, result["failed_reference_count"])

    def test_requires_no_match_confidence_for_empty_targets(self):
        with self.assertRaisesRegex(ValueError, "require no-match"):
            ReferenceLinkAssessment(
                target_block_ids=[], confidence="medium", rationale="No exact candidate."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)