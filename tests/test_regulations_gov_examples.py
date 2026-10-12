"""Tests for the human-readable Regulations.gov API example."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


REPOSITORY_ROOT = Path(__file__).parents[1]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "regulation_gov_results"


def _load_example_module():
    script_path = EXAMPLE_ROOT / "download_examples.py"
    specification = importlib.util.spec_from_file_location(
        "regulations_gov_example_downloader", script_path
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class RegulationsGovExamplesTest(unittest.TestCase):
    def test_download_json_sends_key_and_encodes_parameters(self):
        module = _load_example_module()
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        payload = {"data": {"id": "TEST-1"}}
        with patch.object(module, "urlopen", return_value=response) as mocked_urlopen, patch.object(
            module.json, "load", return_value=payload
        ):
            result = module.download_json(
                api_key="secret",
                resource_path="comments",
                parameters={"filter[commentOnId]": "opaque id", "page[size]": 5},
            )
        self.assertEqual(payload, result)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual("secret", request.headers["X-api-key"])
        self.assertIn("filter%5BcommentOnId%5D=opaque+id", request.full_url)
        self.assertIn("page%5Bsize%5D=5", request.full_url)

    def test_write_json_is_pretty_printed(self):
        module = _load_example_module()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "nested" / "example.json"
            module.write_json(path=output_path, value={"data": {"id": "TEST-1"}})
            contents = output_path.read_text(encoding="utf-8")
        self.assertIn("\n  ", contents)
        self.assertTrue(contents.endswith("\n"))

    def test_checked_in_snapshot_and_comment_joins(self):
        result_root = EXAMPLE_ROOT / "results"
        manifest = json.loads((result_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(28, len(manifest["categories"]))
        self.assertTrue(all(
            len(category["document_ids"]) == 5
            for category in manifest["categories"]
        ))
        expected_counts = {"documents": 139, "dockets": 121, "comments": 78}
        self.assertEqual(expected_counts, manifest["unique_resource_counts"])
        for resource, expected_count in expected_counts.items():
            self.assertEqual(expected_count, len(list((result_root / resource).glob("*.json"))))
        document_ids = {
            path.stem for path in (result_root / "documents").glob("*.json")
        }
        for comment_path in (result_root / "comments").glob("*.json"):
            comment = json.loads(comment_path.read_text(encoding="utf-8"))["data"]
            self.assertIn(comment["attributes"]["commentOnDocumentId"], document_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
