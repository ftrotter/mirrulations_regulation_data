"""Tests for the simple read-only comment browser."""

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.comment_browser import (  # noqa: E402
    CommentBrowserServer,
    build_comment_catalog,
    display_name_for_submission,
    highest_available_stage,
    search_comments,
)
from mirrulations_markdown.pipeline import STAGE_1, STAGE_2  # noqa: E402


def _record(*, source_object_key, role, person_name, organization, markdown_path):
    record_id = Path(source_object_key).stem.replace("_attachment_1", "")
    return {
        "asset": {
            "source_object_key": source_object_key,
            "markdown_path": markdown_path,
            "source_sha256": "hash",
        },
        "document_metadata": {
            "document_id": record_id,
            "logical_document_role": role,
            "representation_role": (
                "metadata_json" if role == "form_comment" else "derived_extraction"
            ),
            "person_name": person_name,
            "organization": organization,
            "title": "Comment",
            "docket_id": "CMS-2026-1255",
            "withdrawn": False,
        },
        "attachment_number": 1 if role == "comment_attachment" else None,
        "blocks": [],
    }
def _corpus(*, root_path):
    markdown_db = root_path / "markdown"
    block_root = markdown_db / "metadata" / "blocks"
    block_root.mkdir(parents=True)
    records = [
        _record(
            source_object_key="comments/CMS-2026-1255-0331.json",
            role="form_comment", person_name="Martha Small",
            organization=None, markdown_path="comments/CMS-2026-1255-0331.json.md",
        ),
        _record(
            source_object_key="comments/CMS-2026-1255-0331_attachment_1.txt",
            role="comment_attachment", person_name="Martha Small",
            organization=None,
            markdown_path="comments/CMS-2026-1255-0331_attachment_1.txt.md",
        ),
    ]
    for index, record in enumerate(records):
        block_root.joinpath(f"record-{index}.json").write_text(json.dumps(record))
    for record in records:
        stage_path = markdown_db / STAGE_1 / record["asset"]["markdown_path"]
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        stage_path.write_text(
            f"prior authorization text for {record['asset']['markdown_path']}"
        )
    return markdown_db


class CommentBrowserTest(unittest.TestCase):
    def test_groups_form_comment_and_attachment_under_one_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = _corpus(root_path=Path(directory))
            representations, submissions = build_comment_catalog(
                markdown_db_path=markdown_db
            )
            self.assertEqual(2, len(representations))
            self.assertEqual(1, len(submissions))
            self.assertEqual(2, len(submissions[0]["representations"]))

    def test_display_name_falls_back_to_organization(self):
        submission = {"person_name": None, "organization": "NACDS"}
        self.assertEqual("NACDS", display_name_for_submission(submission=submission))
        submission = {"person_name": None, "organization": None}
        self.assertEqual(
            "Submitter name not provided",
            display_name_for_submission(submission=submission),
        )

    def test_search_finds_attachment_by_substring(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = _corpus(root_path=Path(directory))
            representations, _submissions = build_comment_catalog(
                markdown_db_path=markdown_db
            )
            results = search_comments(
                markdown_db_path=markdown_db, representations=representations,
                query="prior authorization",
            )
            self.assertEqual(2, len(results))

    def test_highest_available_stage_is_absent_when_no_files(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = _corpus(root_path=Path(directory))
            representations, _submissions = build_comment_catalog(
                markdown_db_path=markdown_db
            )
            for stage_name in (STAGE_1, STAGE_2):
                stage_dir = markdown_db / stage_name
                if stage_dir.is_dir():
                    stage_dir.rename(markdown_db / (stage_name + "-gone"))
            self.assertIsNone(highest_available_stage(
                markdown_db_path=markdown_db, representation=representations[0],
            ))


    def test_http_server_serves_landing_table_and_search(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_db = _corpus(root_path=Path(directory))
            server = CommentBrowserServer(markdown_db_path=markdown_db, port=0)
            host, port = server.httpd.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://{host}:{port}/comments/") as response:
                    page = response.read().decode("utf-8")
                self.assertIn("Comments", page)
                self.assertIn("Martha Small", page)
                with urlopen(
                    f"http://{host}:{port}/comments/search?q=prior+authorization"
                ) as response:
                    results = response.read().decode("utf-8")
                self.assertIn("Search results", results)
                self.assertIn("prior authorization", results)
                with urlopen(
                    f"http://{host}:{port}/comments/CMS-2026-1255-0331/"
                ) as response:
                    submission_page = response.read().decode("utf-8")
                self.assertIn("Representations", submission_page)
            finally:
                server.httpd.shutdown()
                server.httpd.server_close()


if __name__ == "__main__":
    unittest.main()
