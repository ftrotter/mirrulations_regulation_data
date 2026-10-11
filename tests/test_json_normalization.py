"""Tests for post-verification in-place JSON normalization."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.inventory import inventory_fingerprint, inventory_source  # noqa: E402
from mirrulations_markdown.json_normalization import normalize_json_sources  # noqa: E402
from mirrulations_markdown.verification import require_verified_manifest  # noqa: E402


class JsonNormalizationTest(unittest.TestCase):
    def test_pretty_prints_and_preserves_original_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            json_path = source / "raw-data/CMS/CMS-1-0001/item.json"
            json_path.parent.mkdir(parents=True)
            json_path.write_text('{"b":2,"a":1}', encoding="utf-8")
            assets = inventory_source(source_root=source, docket_id="CMS-1-0001")
            manifest_path = root / "verification.json"
            manifest_path.write_text(json.dumps({
                "verified": True, "docket_id": "CMS-1-0001",
                "source_root": str(source.resolve()), "text_only": False,
                "source_inventory_fingerprint": inventory_fingerprint(assets=assets),
            }), encoding="utf-8")
            result = normalize_json_sources(
                source_root=source, docket_id="CMS-1-0001",
                verification_manifest_path=manifest_path,
            )
            self.assertEqual('{\n  "a": 1,\n  "b": 2\n}\n', json_path.read_text())
            self.assertNotEqual(
                result["records"][0]["original_sha256"],
                result["records"][0]["normalized_sha256"],
            )
            require_verified_manifest(manifest_path=manifest_path, source_root=source)
            with self.assertRaisesRegex(ValueError, "already normalized"):
                normalize_json_sources(
                    source_root=source, docket_id="CMS-1-0001",
                    verification_manifest_path=manifest_path,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)