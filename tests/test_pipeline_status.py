"""Tests for authoritative cross-stage pipeline status."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.pipeline import STAGE_1, STAGE_2  # noqa: E402
from mirrulations_markdown.pipeline_status import (  # noqa: E402
    format_pipeline_status, pipeline_status,
)
from mirrulations_markdown.reference_linker import STAGE_4  # noqa: E402
from mirrulations_markdown.structure_pipeline import STAGE_3  # noqa: E402


def _write_json(*, path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class PipelineStatusTest(unittest.TestCase):
    def test_reports_nested_premium_benchmark_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_db, _asset = self._corpus(root=root)
            benchmark_root = markdown_db / "metadata/reference_link_benchmarks"
            _write_json(
                path=benchmark_root / "benchmark-50-comments/manifest.json",
                value={"comment_count": 50, "reference_count": 504},
            )
            _write_json(
                path=(benchmark_root / "openai/test-model/context/batches/batch-one.json"),
                value={"links": [
                    {"reference_id": "reference-1"},
                    {"reference_id": "reference-2"},
                ]},
            )
            _write_json(
                path=(benchmark_root / "openai/test-model/context/rejected_batches/bad.json"),
                value={"validation_error": "bad target"},
            )
            runtime = root / "runtime"
            process_root = runtime / "mirrulations-stage4-50"
            process_root.mkdir(parents=True)
            (process_root / "openai.pid").write_text(str(__import__("os").getpid()))
            (process_root / "openai.log").write_text(
                "Batch 1/51 complete\nBatch 2/51 complete\n"
            )
            status = pipeline_status(
                markdown_db_path=markdown_db, runtime_directory=runtime,
            )
            process = status["premium_benchmark_processes"][0]
            self.assertTrue(process["running"])
            self.assertEqual("openai", process["provider"])
            self.assertEqual(2, process["accepted_references"])
            self.assertEqual(504, process["cohort_references"])
            self.assertEqual(1, process["rejected_batch_files"])
            rendered = format_pipeline_status(status=status)
            self.assertIn("openai: running", rendered)
            self.assertIn("2/504 accepted references", rendered)
            self.assertIn("Latest: Batch 2/51 complete", rendered)

    def _corpus(self, *, root):
        markdown_db = root / "markdown"
        asset = {
            "source_object_key": "comments/COMMENT-1.json",
            "source_sha256": "hash", "markdown_path": "comments/COMMENT-1.json.md",
        }
        blocks = [
            {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
             "plain_text": "The seven-day deadline is too long."},
        ]
        _write_json(
            path=markdown_db / "metadata/blocks/document.json",
            value={"asset": asset, "blocks": blocks},
        )
        _write_json(
            path=markdown_db / "metadata/manifests/source_inventory.json",
            value={"assets": [asset]},
        )
        _write_json(
            path=markdown_db / "metadata/runs/latest.json",
            value={"failed_asset_count": 0},
        )
        _write_json(
            path=markdown_db / "metadata/annotations/citations/document.json",
            value={"citations": []},
        )
        for stage in (STAGE_1, STAGE_2):
            path = markdown_db / stage / asset["markdown_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("text", encoding="utf-8")
        return markdown_db, asset

    def test_reports_partial_then_complete_stage_three(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db, asset = self._corpus(root=Path(directory))
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            status = pipeline_status(
                markdown_db_path=markdown_db, runtime_directory=runtime
            )
            self.assertEqual("complete", status["stage001"]["status"])
            self.assertEqual("complete", status["stage002"]["status"])
            self.assertEqual("not-started", status["stage003"]["status"])
            sidecar = {
                "asset": asset,
                "eligibility": {"eligible": True, "exclusion_reason": None},
                "annotations": [],
            }
            _write_json(
                path=(markdown_db / "metadata/structure_discovery/annotations/document.json"),
                value=sidecar,
            )
            stage_3_path = markdown_db / STAGE_3 / asset["markdown_path"]
            stage_3_path.parent.mkdir(parents=True, exist_ok=True)
            stage_3_path.write_text("text")
            partial = pipeline_status(
                markdown_db_path=markdown_db, runtime_directory=runtime
            )
            self.assertEqual("partial", partial["stage003"]["status"])
            self.assertEqual(1, partial["stage003"]["missing_owned_blocks"])
            sidecar["annotations"] = [{
                "block_id": "paragraph-0001", "segment_task_hash": "segment-hash",
                "task_status": "complete", "backward_references": [{
                    "source_block_id": "paragraph-0001",
                    "target_key": "document:TARGET-1",
                    "search_description": "the seven-day deadline",
                }],
            }]
            _write_json(
                path=(markdown_db / "metadata/structure_discovery/annotations/document.json"),
                value=sidecar,
            )
            complete = pipeline_status(
                markdown_db_path=markdown_db, runtime_directory=runtime
            )
            self.assertEqual("complete", complete["stage003"]["status"])
            self.assertEqual("not-started", complete["stage004"]["status"])

    def test_reports_stale_target_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_db, asset = self._corpus(root=root)
            block_path = markdown_db / "metadata/blocks/document.json"
            block_record = json.loads(block_path.read_text())
            block_record["target_registry"] = [{"target_key": "document:NEW"}]
            _write_json(path=block_path, value=block_record)
            _write_json(
                path=markdown_db / "metadata/structure_discovery/annotations/document.json",
                value={
                    "asset": asset,
                    "eligibility": {"eligible": True, "exclusion_reason": None},
                    "target_registry": [{"target_key": "document:OLD"}],
                    "annotations": [{
                        "block_id": "paragraph-0001",
                        "segment_task_hash": "segment-hash", "task_status": "complete",
                        "backward_references": [],
                    }],
                },
            )
            status = pipeline_status(
                markdown_db_path=markdown_db, runtime_directory=root / "runtime"
            )
        self.assertEqual("partial", status["stage003"]["status"])
        self.assertEqual(1, status["stage003"]["stale_target_registries"])
        self.assertTrue(status["stage004"]["upstream_stage3_stale"])

    def test_reports_complete_stage_four(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db, asset = self._corpus(root=Path(directory))
            _write_json(
                path=markdown_db / "metadata/structure_discovery/annotations/document.json",
                value={
                    "asset": asset,
                    "eligibility": {"eligible": True, "exclusion_reason": None},
                    "annotations": [{
                        "block_id": "paragraph-0001", "segment_task_hash": "segment-hash",
                        "task_status": "complete", "backward_references": [{
                            "source_block_id": "paragraph-0001",
                            "target_key": "document:TARGET-1",
                            "search_description": "the seven-day deadline",
                        }],
                    }],
                },
            )
            _write_json(
                path=markdown_db / "metadata/reference_links/document.json",
                value={
                    "asset": asset,
                    "links": [{
                        "source_block_id": "paragraph-0001",
                        "target_key": "document:TARGET-1",
                        "search_description": "the seven-day deadline",
                        "status": "no-match", "targets": [],
                    }],
                },
            )
            for stage in (STAGE_3, STAGE_4):
                path = markdown_db / stage / asset["markdown_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("text")
            status = pipeline_status(
                markdown_db_path=markdown_db,
                runtime_directory=Path(directory) / "missing-runtime",
            )
            self.assertEqual("complete", status["stage004"]["status"])
            self.assertEqual(1, status["stage004"]["no_match"])
            self.assertIn("Stage 4: complete", format_pipeline_status(status=status))


if __name__ == "__main__":
    unittest.main(verbosity=2)