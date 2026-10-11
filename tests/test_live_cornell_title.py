"""Opt-in one-request validation of Cornell LII title retrieval."""

import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.reference_metadata import (  # noqa: E402
    fetch_official_title,
    title_matches_reference,
)


@unittest.skipUnless(
    os.getenv("MIRRULATIONS_LIVE_CORNELL_TEST") == "1",
    "Set MIRRULATIONS_LIVE_CORNELL_TEST=1 for the one-request live test.",
)
class LiveCornellTitleTest(unittest.TestCase):
    def test_cfr_title_matches_requested_authority(self):
        result = fetch_official_title(
            url="https://www.law.cornell.edu/cfr/text/42/482.24"
        )
        self.assertTrue(
            title_matches_reference(
                title=result["official_reference_name"],
                normalized_target="cfr:42:482.24",
            )
        )
        self.assertIn("Medical record services", result["official_reference_name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)