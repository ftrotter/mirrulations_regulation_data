"""Generic tests applied to every discoverable parser regression case."""

import unittest

from tests.fixture_harness import (
    discover_cases, load_case, render_case, validate_case_hashes,
)


class RegressionCaseManifestTest(unittest.TestCase):
    def test_cases_have_valid_manifests_and_hashes(self):
        cases = discover_cases()
        self.assertTrue(cases, "No regression fixture cases were discovered")
        for manifest_path in cases:
            with self.subTest(case=manifest_path.parent.name):
                case = load_case(manifest_path=manifest_path)
                self.assertEqual(manifest_path.parent.name, case["case_id"])
                self.assertTrue(case["public_source"]["public_record_notice"])
                validate_case_hashes(manifest_path=manifest_path, case=case)

    def test_cases_meet_structural_assertions(self):
        for manifest_path in discover_cases():
            with self.subTest(case=manifest_path.parent.name):
                case = load_case(manifest_path=manifest_path)
                blocks, markdown = render_case(manifest_path=manifest_path, case=case)
                if blocks is None:  # PDF-only cases are covered by pypdf-specific tests.
                    continue
                for forbidden in case["expected"].get("forbidden_patterns", []):
                    self.assertNotIn(forbidden, markdown)
                for required in case["expected"].get("required_patterns", []):
                    self.assertIn(required, markdown)
                self.assertTrue(all(block["block_type"] != "table-row" for block in blocks))
                self.assertTrue(
                    all(
                        block["plain_text"].strip()
                        for block in blocks
                        if block["block_type"] == "list-item"
                    )
                )
                self.assertNotIn("\n- \n", markdown)


if __name__ == "__main__":
    unittest.main(verbosity=2)