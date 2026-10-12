"""Tests for the reproducible sampled Stage 3 review runner."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.pipeline import STAGE_1, STAGE_2  # noqa: E402
from mirrulations_markdown.stage3_review_runner import Stage3ReviewRunner  # noqa: E402
from mirrulations_markdown.structure_models import (  # noqa: E402
    ModelSpec, StructureConfiguration,
)


def _configuration():
    model = ModelSpec(provider="openai", model="test")
    return StructureConfiguration(summary_model=model, reference_model=model)


def _record(*, source_object_key, role):
    return {
        "asset": {
            "source_object_key": source_object_key,
            "source_sha256": "hash",
            "markdown_path": f"{source_object_key}.md",
            "selection_reason": "test",
        },
        "document_metadata": {"logical_document_role": role},
        "blocks": [{
            "block_id": "paragraph-0001", "block_type": "paragraph",
            "order": 1, "plain_text": "Substantive comment text.",
        }],
        "target_registry": [],
    }


class Stage3ReviewRunnerTest(unittest.TestCase):
    def test_selection_is_deterministic_and_includes_every_role(self):
        records = [
            *[
                _record(source_object_key=f"comments/form-{number}.json", role="form_comment")
                for number in range(12)
            ],
            *[
                _record(
                    source_object_key=f"comments/attachment-{number}_attachment_1.txt",
                    role="comment_attachment",
                )
                for number in range(7)
            ],
            _record(source_object_key="documents/rule.html", role="regulatory_document"),
        ]
        _eligible, first = Stage3ReviewRunner.select_cohort(
            block_records=records, configuration=_configuration(), sample_fraction=0.20
        )
        _eligible, second = Stage3ReviewRunner.select_cohort(
            block_records=list(reversed(records)),
            configuration=_configuration(), sample_fraction=0.20,
        )
        first_keys = [record["asset"]["source_object_key"] for record in first]
        second_keys = [record["asset"]["source_object_key"] for record in second]
        self.assertEqual(first_keys, second_keys)
        self.assertEqual(4, len(first))
        self.assertEqual(
            {"form_comment", "comment_attachment", "regulatory_document"},
            {record["document_metadata"]["logical_document_role"] for record in first},
        )

    def test_preflight_failure_writes_report_before_stage_three_changes(self):
        async def failing_caller(**_kwargs):
            raise RuntimeError("provider unavailable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markdown_db = root / "markdown"
            source_root = root / "source"
            output_directory = markdown_db / "metadata" / "review"
            source_root.mkdir()
            (source_root / "source.txt").write_text("source", encoding="utf-8")
            for stage_name in (STAGE_1, STAGE_2):
                stage_root = markdown_db / stage_name
                stage_root.mkdir(parents=True)
                (stage_root / "existing.md").write_text("existing", encoding="utf-8")
            blocks_root = markdown_db / "metadata" / "blocks"
            blocks_root.mkdir(parents=True)
            blocks_root.joinpath("record.json").write_text(
                json.dumps(_record(
                    source_object_key="comments/form-1.json", role="form_comment"
                )),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "RuntimeError"):
                Stage3ReviewRunner.run(
                    markdown_db_path=markdown_db,
                    source_root=source_root,
                    configuration=_configuration(),
                    output_directory=output_directory,
                    sample_fraction=1.0,
                    segment_caller=failing_caller,
                )
            report = json.loads(
                (output_directory / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual("failed", report["status"])
            self.assertFalse((markdown_db / "metadata/structure_discovery").exists())


if __name__ == "__main__":
    unittest.main()