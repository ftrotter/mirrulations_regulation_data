"""Tests for coherent section and list-aware LLM segments."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.analysis_segments import build_analysis_segments  # noqa: E402


def _block(*, block_id, block_type, text):
    return {"block_id": block_id, "block_type": block_type, "plain_text": text}


class AnalysisSegmentTest(unittest.TestCase):
    def test_keeps_small_section_together(self):
        blocks = [
            _block(block_id="section-0001", block_type="section", text="I. Timing"),
            _block(block_id="paragraph-0001", block_type="paragraph", text="Intro"),
            _block(block_id="list-0001", block_type="list", text="- One\n- Two"),
            _block(block_id="paragraph-0002", block_type="paragraph", text="Conclusion"),
        ]
        segments = build_analysis_segments(blocks=blocks)
        self.assertEqual(1, len(segments))
        self.assertEqual(
            ["paragraph-0001", "list-0001", "paragraph-0002"],
            segments[0]["owned_block_ids"],
        )
        self.assertEqual("I. Timing", segments[0]["section_heading"])

    def test_unstructured_document_chunks_ten_with_overlap(self):
        blocks = [
            _block(
                block_id=f"paragraph-{number:04d}", block_type="paragraph",
                text=f"Paragraph {number}",
            )
            for number in range(1, 13)
        ]
        segments = build_analysis_segments(blocks=blocks)
        self.assertEqual([10, 2], [len(segment["owned_block_ids"]) for segment in segments])
        self.assertEqual(
            "context_only", segments[1]["blocks"][0]["analysis_role"]
        )
        self.assertEqual("paragraph-0010", segments[1]["blocks"][0]["block_id"])

    def test_oversized_section_splits_without_splitting_list(self):
        blocks = [
            _block(block_id="section-0001", block_type="section", text="I. Details"),
            _block(block_id="paragraph-0001", block_type="paragraph", text="A" * 20),
            _block(block_id="list-0001", block_type="list", text="- " + "B" * 40),
            _block(block_id="paragraph-0002", block_type="paragraph", text="C" * 20),
        ]
        segments = build_analysis_segments(
            blocks=blocks, maximum_owned_blocks=20, maximum_characters=50
        )
        self.assertEqual(3, len(segments))
        self.assertEqual(["list-0001"], segments[1]["owned_block_ids"])

    def test_list_receives_label_and_neighboring_paragraph_context(self):
        blocks = [
            _block(block_id="paragraph-0001", block_type="paragraph", text="Before"),
            _block(block_id="label-0001", block_type="label", text="Recommendations:"),
            _block(block_id="list-0001", block_type="list", text="- One\n- Two"),
            _block(block_id="paragraph-0002", block_type="paragraph", text="After"),
        ]
        segments = build_analysis_segments(
            blocks=blocks, unstructured_owned_blocks=1
        )
        list_segment = next(
            segment for segment in segments if segment["owned_block_ids"] == ["list-0001"]
        )
        self.assertEqual(
            ["paragraph-0001", "label-0001", "list-0001", "paragraph-0002"],
            [block["block_id"] for block in list_segment["blocks"]],
        )
        self.assertEqual(
            ["context_only", "context_only", "owned", "context_only"],
            [block["analysis_role"] for block in list_segment["blocks"]],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)