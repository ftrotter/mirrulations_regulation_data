"""Tests for Stage 3 structure discovery and Magentic-compatible calling."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.pipeline import STAGE_2  # noqa: E402
from mirrulations_markdown.structure_models import (  # noqa: E402
    ModelSpec,
    PassageEnrichment,
    StructureConfiguration,
)
from mirrulations_markdown.structure_pipeline import (  # noqa: E402
    STAGE_3,
    StructureDiscoveryPipeline,
    document_eligibility,
)


def _configuration(*, max_pages=50, summary_mode="deep"):
    model = ModelSpec(provider="openai", model="test-model")
    return StructureConfiguration(
        summary_model=model,
        reference_model=model,
        summary_mode=summary_mode,
        max_comment_pages=max_pages,
    )


class EligibilityTest(unittest.TestCase):
    def test_exact_page_limit_is_eligible(self):
        record = {
            "asset": {"source_object_key": "derived/comments_extracted_text/item.txt"},
            "alignment": {"page_count": 50},
            "blocks": [{"plain_text": "text"}],
        }
        result = document_eligibility(
            block_record=record, configuration=_configuration()
        )
        self.assertTrue(result.eligible)
        self.assertEqual("actual", result.page_count_method)

    def test_estimated_page_limit_excludes_long_comment(self):
        record = {
            "asset": {"source_object_key": "raw/comments/item.json"},
            "alignment": None,
            "blocks": [{"plain_text": "x" * 6001}],
        }
        result = document_eligibility(
            block_record=record, configuration=_configuration(max_pages=2)
        )
        self.assertFalse(result.eligible)
        self.assertEqual(3, result.page_count)
        self.assertEqual("estimated", result.page_count_method)


class StructurePipelineTest(unittest.TestCase):
    def _create_corpus(self, *, root_path, long_comment=False):
        markdown_db_path = root_path / "markdown"
        source_key = "raw-data/CMS/docket/text/comments/COMMENT-1.json"
        markdown_path = f"{source_key}.md"
        stage_2_path = markdown_db_path / STAGE_2 / markdown_path
        stage_2_path.parent.mkdir(parents=True)
        source_text = "x" * 6001 if long_comment else "The deadline is too short."
        stage_2_text = (
            "---\ndocument_id: \"COMMENT-1\"\n---\n"
            f'<a id="p-0001"></a>\n\n{source_text}\n'
        )
        stage_2_path.write_text(stage_2_text, encoding="utf-8")
        block_name = "block.json"
        block_path = markdown_db_path / "metadata" / "blocks" / block_name
        block_path.parent.mkdir(parents=True)
        block_path.write_text(
            json.dumps(
                {
                    "asset": {
                        "source_object_key": source_key,
                        "source_sha256": "hash",
                        "markdown_path": markdown_path,
                        "selection_reason": "form-submitted-comment-body",
                    },
                    "alignment": None,
                    "blocks": [
                        {
                            "block_id": "p-0001",
                            "block_type": "paragraph",
                            "plain_text": source_text,
                            "heading_context": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return markdown_db_path, stage_2_path, stage_2_text, markdown_path

    def test_renders_stage_three_and_reuses_completed_annotation(self):
        calls = []

        async def fake_caller(**kwargs):
            calls.append(kwargs)
            return PassageEnrichment(
                summary="The commenter argues that the deadline is too short.",
                backward_references=[
                    "Look for the proposed implementation deadline."
                ],
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, stage_2_path, stage_2_before, markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            first = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(),
                passage_caller=fake_caller,
            )
            second = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(),
                passage_caller=fake_caller,
            )
            output = (markdown_db_path / STAGE_3 / markdown_path).read_text(
                encoding="utf-8"
            )
            self.assertEqual(1, first["api_calls"])
            self.assertEqual(0, second["api_calls"])
            self.assertEqual(1, len(calls))
            self.assertIn("**In brief:**", output)
            self.assertIn("**Reference:**", output)
            self.assertGreater(output.index("**In brief:**"), output.index('<a id="p-0001"></a>'))
            self.assertEqual(stage_2_before, stage_2_path.read_text(encoding="utf-8"))

    def test_section_mode_document_summary_precedes_headingless_source(self):
        async def fake_caller(**_kwargs):
            return PassageEnrichment(
                summary="The commenter argues that the deadline is too short.",
                backward_references=[],
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(summary_mode="sections"),
                passage_caller=fake_caller,
            )
            output = (markdown_db_path / STAGE_3 / markdown_path).read_text(
                encoding="utf-8"
            )
            self.assertLess(
                output.index("**In brief:**"), output.index('<a id="p-0001"></a>')
            )

    def test_excluded_comment_makes_no_api_call(self):
        async def caller_that_must_not_run(**_kwargs):
            raise AssertionError("caller should not run")

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, markdown_path = (
                self._create_corpus(
                    root_path=Path(temporary_directory), long_comment=True
                )
            )
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(max_pages=2),
                passage_caller=caller_that_must_not_run,
            )
            output = (markdown_db_path / STAGE_3 / markdown_path).read_text(
                encoding="utf-8"
            )
            self.assertEqual(0, status["api_calls"])
            self.assertEqual(1, status["excluded_documents"])
            self.assertIn("**Processing status:** excluded-length", output)

    def test_source_object_filter_can_select_no_documents(self):
        async def caller_that_must_not_run(**_kwargs):
            raise AssertionError("caller should not run")

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, _markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(),
                passage_caller=caller_that_must_not_run,
                source_object_key="does/not/exist",
            )
            self.assertEqual(0, status["selected_documents"])
            self.assertEqual(0, status["api_calls"])

    def test_source_prefix_filter_selects_matching_document(self):
        async def fake_caller(**_kwargs):
            return PassageEnrichment(
                summary="This is a complete summary.", backward_references=[]
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, _markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(), passage_caller=fake_caller,
                source_object_prefix="raw-data/CMS/",
            )
            self.assertEqual(1, status["selected_documents"])

    def test_api_call_budget_stops_before_second_call(self):
        calls = []

        async def fake_caller(**kwargs):
            calls.append(kwargs)
            return PassageEnrichment(
                summary="This is a complete summary.", backward_references=[]
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, _markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            block_path = next((markdown_db_path / "metadata/blocks").glob("*.json"))
            record = json.loads(block_path.read_text(encoding="utf-8"))
            record["blocks"].append(
                {
                    "block_id": "p-0002", "block_type": "paragraph",
                    "plain_text": "A second passage.", "heading_context": [],
                }
            )
            block_path.write_text(json.dumps(record), encoding="utf-8")
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(), passage_caller=fake_caller,
                maximum_api_calls=1,
            )
            self.assertEqual(1, status["api_calls"])
            self.assertEqual(1, len(calls))
            self.assertEqual(1, status["failed_task_count"])
            self.assertIn("budget exhausted", status["failed_tasks"][0]["error"])

    def test_failed_model_attempt_consumes_budget_and_sanitizes_error(self):
        async def failing_caller(**_kwargs):
            raise RuntimeError("raw provider payload must not be retained")

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, _markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(), passage_caller=failing_caller,
                maximum_api_calls=1,
            )
            self.assertEqual(1, status["api_calls"])
            self.assertEqual(1, status["failed_task_count"])
            self.assertNotIn("raw provider payload", status["failed_tasks"][0]["error"])

    def test_fractional_pacing_and_progress_events(self):
        current_time = [0.0]
        sleeps = []
        events = []

        def clock():
            return current_time[0]

        def sleeper(seconds):
            sleeps.append(seconds)
            current_time[0] += seconds

        async def fake_caller(**_kwargs):
            return PassageEnrichment(
                summary="This is a complete summary.", backward_references=[]
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, _markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            block_path = next((markdown_db_path / "metadata/blocks").glob("*.json"))
            record = json.loads(block_path.read_text(encoding="utf-8"))
            record["blocks"].append({
                "block_id": "p-0002", "block_type": "paragraph",
                "plain_text": "Second passage.", "heading_context": [],
            })
            block_path.write_text(json.dumps(record), encoding="utf-8")
            status = StructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=_configuration(), passage_caller=fake_caller,
                maximum_api_calls=2, requests_per_second=0.5,
                progress_callback=events.append, sleeper=sleeper, clock=clock,
            )
            self.assertEqual([2.0], sleeps)
            self.assertEqual(2, status["api_calls"])
            self.assertEqual(2.0, status["elapsed_seconds"])
            self.assertIn("document_started", [event["event"] for event in events])
            self.assertEqual(
                2,
                sum(event["event"] == "api_call_completed" for event in events),
            )

    def test_rejects_nonpositive_request_rate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, *_rest = self._create_corpus(
                root_path=Path(temporary_directory)
            )
            with self.assertRaisesRegex(ValueError, "greater than zero"):
                StructureDiscoveryPipeline.run(
                    markdown_db_path=markdown_db_path,
                    configuration=_configuration(), passage_caller=lambda **_kwargs: None,
                    requests_per_second=0,
                )

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_live_caller_preflight_rejects_missing_credentials_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            markdown_db_path, _stage_2_path, _stage_2_text, markdown_path = (
                self._create_corpus(root_path=Path(temporary_directory))
            )
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                StructureDiscoveryPipeline.run(
                    markdown_db_path=markdown_db_path,
                    configuration=_configuration(),
                )
            self.assertFalse((markdown_db_path / STAGE_3 / markdown_path).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)