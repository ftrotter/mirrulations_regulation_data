"""Tests for independent OpenAI review of production Stage 4 results."""

import json
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.stage4_quality_review import (  # noqa: E402
    Stage4QualityReviewRunner, Stage4ReviewJudgment, select_review_sample,
)


class FakeReviewer:
    def __init__(self):
        self.calls = 0
        self.closed = False
        self.event_loop_ids = []

    async def review(self, *, evidence):
        self.event_loop_ids.append(id(asyncio.get_running_loop()))
        self.calls += 1
        status = evidence["production_stage4"]["status"]
        return {
            "judgment": Stage4ReviewJudgment(
                classification=(
                    "correct_exact_link" if status == "linked" else "correct_no_match"
                ),
                source_description_consistent=True,
                production_decision_correct=True,
                rationale="The production decision matches the supplied evidence.",
            ),
            "response_id": f"response-{self.calls}",
            "model_version": "test-model",
        }

    async def aclose(self):
        self.closed = True


class Stage4QualityReviewTest(unittest.TestCase):
    def test_selection_is_deterministic_and_stratified(self):
        records = [
            {"selection_hash": f"{index:02d}", "link": {"status": status}}
            for status in ("linked", "no-match") for index in range(5)
        ]
        first = select_review_sample(records=records, linked_count=2, no_match_count=1)
        second = select_review_sample(
            records=list(reversed(records)), linked_count=2, no_match_count=1,
        )
        self.assertEqual(first, second)
        self.assertEqual(["linked", "linked", "no-match"], [
            record["link"]["status"] for record in first
        ])

    def test_run_checkpoints_and_reuses_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = self._write_corpus(root_path=Path(directory))
            output_directory = Path(directory) / "review"
            first_reviewer = FakeReviewer()
            first = Stage4QualityReviewRunner.run(
                markdown_db_path=markdown_db, output_directory=output_directory,
                model="test-model", linked_count=1, no_match_count=1,
                reviewer=first_reviewer,
            )
            self.assertEqual(2, first_reviewer.calls)
            self.assertEqual(1, len(set(first_reviewer.event_loop_ids)))
            self.assertTrue(first_reviewer.closed)
            self.assertEqual("complete", first["status"])
            self.assertEqual(100.0, first["production_decision_correct_percent"])
            second_reviewer = FakeReviewer()
            second = Stage4QualityReviewRunner.run(
                markdown_db_path=markdown_db, output_directory=output_directory,
                model="test-model", linked_count=1, no_match_count=1,
                reviewer=second_reviewer,
            )
            self.assertEqual(0, second_reviewer.calls)
            self.assertEqual(first, second)
            self.assertTrue((output_directory / "report.md").is_file())

    @staticmethod
    def _write_corpus(*, root_path):
        markdown_db = root_path / "markdown"
        block_root = markdown_db / "metadata/blocks"
        link_root = markdown_db / "metadata/reference_links"
        block_root.mkdir(parents=True)
        link_root.mkdir(parents=True)
        target_key = "raw-data/CMS/docket/documents/TARGET-1_content.html"
        source_key = "raw-data/CMS/docket/comments/COMMENT-1.json"
        target = {
            "asset": {"source_object_key": target_key},
            "blocks": [
                {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
                 "heading_context": [], "plain_text": "General background."},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 2,
                 "heading_context": ["Deadline"], "plain_text": "We propose seven days."},
                {"block_id": "paragraph-0003", "block_type": "paragraph", "order": 3,
                 "heading_context": [], "plain_text": "Additional detail."},
            ],
        }
        source = {
            "asset": {"source_object_key": source_key},
            "blocks": [
                {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
                 "heading_context": [], "plain_text": "Seven days is too long."},
                {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 2,
                 "heading_context": [], "plain_text": "No exact provision is discussed."},
            ],
        }
        (block_root / "target.json").write_text(json.dumps(target))
        (block_root / "source.json").write_text(json.dumps(source))
        links = {
            "asset": source["asset"],
            "links": [
                {"link_hash": "linked-hash", "status": "linked",
                 "source_block_id": "paragraph-0001", "target_key": "document:TARGET-1",
                 "search_description": "the seven-day deadline", "confidence": "high",
                 "rationale": "Exact deadline.",
                 "targets": [{"target_block_id": "paragraph-0002"}]},
                {"link_hash": "no-match-hash", "status": "no-match",
                 "source_block_id": "paragraph-0002", "target_key": "document:TARGET-1",
                 "search_description": "an unrelated provision", "confidence": "no-match",
                 "rationale": "No candidate matched.", "targets": []},
            ],
        }
        (link_root / "source.json").write_text(json.dumps(links))
        return markdown_db


if __name__ == "__main__":
    unittest.main(verbosity=2)