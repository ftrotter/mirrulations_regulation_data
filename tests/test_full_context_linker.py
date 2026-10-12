"""Tests for provider-neutral full-context Stage 4 behavior."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.full_context_linker import (  # noqa: E402
    FullContextLinkBatch,
    FullContextLinkResult,
    LINKING_INSTRUCTIONS,
    RelationshipEvidence,
    identify_open_questions,
    serialize_target_context,
    validate_link_batch,
)


class FullContextLinkerTest(unittest.TestCase):
    def setUp(self):
        self.blocks = [
            {"block_id": "section-0001", "block_type": "section", "order": 1,
             "plain_text": "Reporting metrics"},
            {"block_id": "paragraph-0001", "block_type": "paragraph", "order": 2,
             "plain_text": "We expect aggregate reporting to reduce burden."},
            {"block_id": "paragraph-0002", "block_type": "paragraph", "order": 3,
             "plain_text": "We request comment on whether specialty-level metrics are needed."},
        ]
        self.questions = identify_open_questions(target_blocks=self.blocks)
        self.evidence = RelationshipEvidence(
            comment_position="Specialty-level reporting is necessary.",
            agency_position="The agency asks whether specialty-level metrics are needed.",
            link_explanation="The comment directly answers the invitation.",
        )

    def test_skylines_agency_question_but_not_background_expectation(self):
        self.assertEqual(1, len(self.questions))
        self.assertEqual(["paragraph-0002"], self.questions[0].question_target_ids)
        self.assertEqual(["paragraph-0001"], self.questions[0].supporting_target_ids)

    def test_does_not_treat_historical_rfi_mention_as_question(self):
        questions = identify_open_questions(target_blocks=[{
            "block_id": "paragraph-0001", "block_type": "paragraph", "order": 1,
            "plain_text": "The 2020 request for information discussed this topic.",
        }])
        self.assertEqual([], questions)

    def test_serialization_is_deterministic_and_skylines_question(self):
        first = serialize_target_context(document_id="TARGET-1", target_blocks=self.blocks)
        second = serialize_target_context(
            document_id="TARGET-1", target_blocks=list(reversed(self.blocks))
        )
        self.assertEqual(first["context_sha256"], second["context_sha256"])
        self.assertIn('discourse_role="explicit_open_question"', first["serialized_context"])
        self.assertIn("OPEN QUESTION INDEX", first["serialized_context"])

    def test_explicit_question_requires_question_id(self):
        with self.assertRaisesRegex(ValueError, "require an open-question ID"):
            FullContextLinkResult(
                reference_id="reference-1",
                primary_relationship_class="explicit_open_question",
                match_status="linked",
                primary_target_ids=["paragraph-0002"],
                confidence=0.9,
                relationship_evidence=self.evidence,
            )

    def test_accepts_assumption_challenge_with_secondary_class(self):
        result = FullContextLinkResult(
            reference_id="reference-1",
            primary_relationship_class="implicit_assumption_challenge",
            secondary_relationship_classes=["other_substantive_relationship"],
            match_status="linked",
            primary_target_ids=["paragraph-0001"],
            confidence=0.8,
            relationship_evidence=self.evidence,
        )
        self.assertEqual("implicit_assumption_challenge", result.primary_relationship_class)

    def test_validates_coverage_ids_and_question_target(self):
        question = self.questions[0]
        batch = FullContextLinkBatch(results=[FullContextLinkResult(
            reference_id="reference-1",
            primary_relationship_class="explicit_open_question",
            match_status="linked",
            primary_target_ids=["paragraph-0002"],
            open_question_ids=[question.open_question_id],
            confidence=0.95,
            relationship_evidence=self.evidence,
        )])
        validated = validate_link_batch(
            batch=batch,
            expected_reference_ids=["reference-1"],
            target_block_ids=[block["block_id"] for block in self.blocks],
            open_questions=self.questions,
        )
        self.assertIs(batch, validated)

    def test_rejects_question_id_attached_only_to_background(self):
        question = self.questions[0]
        batch = FullContextLinkBatch(results=[FullContextLinkResult(
            reference_id="reference-1",
            primary_relationship_class="explicit_open_question",
            match_status="linked",
            primary_target_ids=["paragraph-0001"],
            open_question_ids=[question.open_question_id],
            confidence=0.5,
            relationship_evidence=self.evidence,
        )])
        with self.assertRaisesRegex(ValueError, "select its question block"):
            validate_link_batch(
                batch=batch,
                expected_reference_ids=["reference-1"],
                target_block_ids=[block["block_id"] for block in self.blocks],
                open_questions=self.questions,
            )

    def test_rejects_invented_target_id(self):
        batch = FullContextLinkBatch(results=[FullContextLinkResult(
            reference_id="reference-1",
            primary_relationship_class="other_substantive_relationship",
            match_status="linked",
            primary_target_ids=["paragraph-9999"],
            confidence=0.5,
            relationship_evidence=self.evidence,
        )])
        with self.assertRaisesRegex(ValueError, "invented target IDs"):
            validate_link_batch(
                batch=batch,
                expected_reference_ids=["reference-1"],
                target_block_ids=[block["block_id"] for block in self.blocks],
                open_questions=self.questions,
            )

    def test_requires_exact_reference_coverage(self):
        batch = FullContextLinkBatch(results=[])
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            validate_link_batch(
                batch=batch,
                expected_reference_ids=["reference-1"],
                target_block_ids=[block["block_id"] for block in self.blocks],
                open_questions=self.questions,
            )

    def test_prompt_contains_all_relationship_classes_and_topical_warning(self):
        self.assertIn("explicit_open_question", LINKING_INSTRUCTIONS)
        self.assertIn("implicit_assumption_challenge", LINKING_INSTRUCTIONS)
        self.assertIn("other_substantive_relationship", LINKING_INSTRUCTIONS)
        self.assertIn("Mere topical similarity is not a link", LINKING_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)