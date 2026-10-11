"""Tests for cached titles and persistent reference friendly names."""

import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.reference_metadata import (  # noqa: E402
    normalized_reference_text, resolve_reference_names,
    title_matches_reference, write_reference_friendly_names,
)


class _Response:
    status = 200
    def __init__(self, body, url): self.body, self.url = body, url
    def read(self): return self.body
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class ReferenceMetadataTest(unittest.TestCase):
    def test_title_identity_accepts_punctuated_usc_name(self):
        self.assertTrue(title_matches_reference(
            title="5 U.S.C. 553 - Rule making", normalized_target="usc:5:553"
        ))
    def test_normalized_reference_fallback(self):
        self.assertEqual("42 CFR § 482.24", normalized_reference_text(normalized_target="cfr:42:482.24"))

    def test_fetches_title_once_and_uses_cache(self):
        calls = []
        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return _Response(
                b"<html><title>42 CFR \xc2\xa7 482.24 - Medical record services.</title></html>",
                request.full_url,
            )
        citation = {
            "normalized_target": "cfr:42:482.24",
            "destination_url": "https://www.law.cornell.edu/cfr/text/42/482.24",
        }
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "titles.json"
            first, first_count = resolve_reference_names(
                citations=[citation], cache_path=cache_path, opener=opener
            )
            second, second_count = resolve_reference_names(
                citations=[citation], cache_path=cache_path, opener=opener
            )
            self.assertEqual(1, len(calls))
            self.assertEqual(first, second)
            self.assertEqual((1, 0), (first_count, second_count))
            self.assertEqual("fetched", first["cfr:42:482.24"]["status"])
            self.assertTrue(first["cfr:42:482.24"]["identity_verified"])

    def test_strips_cornell_site_boilerplate_from_title(self):
        def opener(request, timeout):
            return _Response(
                b"<title>42 CFR 482.24 - Medical records | US Law | LII</title>",
                "https://www.law.cornell.edu/cfr/text/42/482.24",
            )
        with tempfile.TemporaryDirectory() as directory:
            cache, _count = resolve_reference_names(
                citations=[{
                    "normalized_target": "cfr:42:482.24",
                    "destination_url": "https://www.law.cornell.edu/cfr/text/42/482.24",
                }],
                cache_path=Path(directory) / "cache.json", opener=opener,
            )
            self.assertEqual(
                "42 CFR 482.24 - Medical records",
                cache["cfr:42:482.24"]["official_reference_name"],
            )

    def test_fetch_failure_is_cached_with_fallback(self):
        def opener(_request, _timeout): raise OSError("offline")
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "titles.json"
            cache, fetch_count = resolve_reference_names(
                citations=[{"normalized_target": "usc:5:553", "destination_url": "https://example"}],
                cache_path=cache_path, opener=opener,
            )
            self.assertEqual("5 U.S.C. § 553", cache["usc:5:553"]["official_reference_name"])
            self.assertEqual("fetch-failed", cache["usc:5:553"]["status"])
            self.assertEqual(1, fetch_count)

    def test_budget_deferred_title_is_attempted_on_next_run(self):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            return _Response(
                b"<title>42 CFR 482.24 - Medical record services</title>",
                request.full_url,
            )
        citation = {
            "normalized_target": "cfr:42:482.24",
            "destination_url": "https://example/cfr/42/482.24",
        }
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "titles.json"
            first, first_count = resolve_reference_names(
                citations=[citation], cache_path=cache_path,
                maximum_fetches=0, opener=opener,
            )
            second, second_count = resolve_reference_names(
                citations=[citation], cache_path=cache_path,
                maximum_fetches=1, opener=opener,
            )
            self.assertEqual("fetch-deferred-budget", first["cfr:42:482.24"]["status"])
            self.assertEqual((0, 1), (first_count, second_count))
            self.assertEqual("fetched", second["cfr:42:482.24"]["status"])

    def test_preserves_edited_reference_name(self):
        reference = {
            "normalized_target": "cfr:42:482.24", "official_reference_name": "Official",
            "reference_text": "42 CFR § 482.24", "reference_url": "https://example",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.md"
            write_reference_friendly_names(table_path=path, references=[reference])
            path.write_text(path.read_text().replace("| Official |  |", "| Official | Human name |"))
            reference["official_reference_name"] = "Updated official"
            names = write_reference_friendly_names(table_path=path, references=[reference])
            self.assertEqual("Human name", names["cfr:42:482.24"])

    def test_generated_fallback_updates_to_official_name(self):
        reference = {
            "normalized_target": "cfr:42:482.24", "official_reference_name": "Fallback",
            "reference_text": "42 CFR § 482.24", "reference_url": "https://example",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.md"
            write_reference_friendly_names(table_path=path, references=[reference])
            self.assertIn("| Fallback |  |", path.read_text())
            reference["official_reference_name"] = "Fetched official"
            names = write_reference_friendly_names(table_path=path, references=[reference])
            self.assertEqual("Fetched official", names["cfr:42:482.24"])


if __name__ == "__main__": unittest.main(verbosity=2)