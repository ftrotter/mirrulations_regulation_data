"""Tests for revision-aware Regulations.gov resource indexing."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.resource_index import (  # noqa: E402
    build_resource_index, current_resource,
)


def _write_resource(*, root, relative_path, resource_type, public_id, docket_id=None,
                    title=None):
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": {
        "id": public_id, "type": resource_type,
        "attributes": {"docketId": docket_id, "title": title},
    }}), encoding="utf-8")


class ResourceIndexTest(unittest.TestCase):
    def test_selects_highest_revision_and_preserves_null_presence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_resource(
                root=root, relative_path="documents/DOC-1.json",
                resource_type="documents", public_id="DOC-1", title="Old",
            )
            _write_resource(
                root=root, relative_path="documents/DOC-1(2).json",
                resource_type="documents", public_id="DOC-1", title=None,
            )
            index = build_resource_index(source_root=root)
        current = current_resource(
            resource_index=index, resource_type="documents", public_id="DOC-1"
        )
        self.assertEqual(2, current["revision_number"])
        self.assertEqual("explicit-null", current["attribute_presence"]["title"])
        self.assertEqual(2, len(index["resources"][0]["versions"]))

    def test_resource_family_is_part_of_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_resource(
                root=root, relative_path="documents/SAME.json",
                resource_type="documents", public_id="SAME",
            )
            _write_resource(
                root=root, relative_path="comments/SAME.json",
                resource_type="comments", public_id="SAME",
            )
            index = build_resource_index(source_root=root)
        self.assertIsNotNone(current_resource(
            resource_index=index, resource_type="documents", public_id="SAME"
        ))
        self.assertIsNotNone(current_resource(
            resource_index=index, resource_type="comments", public_id="SAME"
        ))

    def test_rejects_wrong_docket(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_resource(
                root=root, relative_path="documents/DOC-1.json",
                resource_type="documents", public_id="DOC-1", docket_id="DOCKET-A",
            )
            index = build_resource_index(source_root=root)
        with self.assertRaisesRegex(ValueError, "does not match"):
            current_resource(
                resource_index=index, resource_type="documents", public_id="DOC-1",
                docket_id="DOCKET-B",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)