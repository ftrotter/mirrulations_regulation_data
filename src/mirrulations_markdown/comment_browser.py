"""Simple read-only comment browser served by the standard library."""

from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .pipeline import STAGE_1, STAGE_2
from .reference_linker import STAGE_4
from .structure_pipeline import STAGE_3


STAGE_5 = "stage005_topic_enrichment"
STAGES = (
    (1, STAGE_1),
    (2, STAGE_2),
    (3, STAGE_3),
    (4, STAGE_4),
    (5, STAGE_5),
)
VALID_STAGE_NUMBERS = {number for number, _directory in STAGES}
RECORD_ID_PATTERN = re.compile(r"[A-Z]+-\d{4}-\d+-\d+")


def _record_id_from_source_key(*, source_object_key):
    match = RECORD_ID_PATTERN.search(Path(source_object_key).name)
    return match.group(0) if match else Path(source_object_key).stem


def build_comment_catalog(*, markdown_db_path):
    """Group comment block records into submissions and representations."""
    block_root = Path(markdown_db_path) / "metadata" / "blocks"
    representations = []
    for block_path in block_root.glob("*.json"):
        record = json.loads(block_path.read_text(encoding="utf-8"))
        metadata = record.get("document_metadata") or {}
        role = metadata.get("logical_document_role")
        if role not in {"form_comment", "comment_attachment"}:
            continue
        asset = record["asset"]
        representations.append({
            "representation_id": block_path.stem,
            "comment_id": metadata.get("document_id")
            or _record_id_from_source_key(source_object_key=asset["source_object_key"]),
            "logical_document_role": role,
            "representation_role": metadata.get("representation_role"),
            "attachment_number": record.get("attachment_number"),
            "source_object_key": asset["source_object_key"],
            "markdown_path": asset["markdown_path"],
            "document_metadata": metadata,
        })
    representations.sort(key=lambda item: (
        item["comment_id"], item["attachment_number"] or 0,
        item["representation_role"] or "",
    ))
    submissions = OrderedDict()
    for representation in representations:
        comment_id = representation["comment_id"]
        if comment_id not in submissions:
            metadata = representation["document_metadata"]
            submissions[comment_id] = {
                "comment_id": comment_id,
                "person_name": metadata.get("person_name"),
                "organization": metadata.get("organization"),
                "title": metadata.get("title"),
                "friendly_name": metadata.get("generated_friendly_name"),
                "docket_id": metadata.get("docket_id"),
                "withdrawn": metadata.get("withdrawn", False),
                "representations": [],
            }
        submissions[comment_id]["representations"].append(representation)
    return representations, list(submissions.values())

def display_name_for_submission(*, submission):
    person_name = submission.get("person_name")
    organization = submission.get("organization")
    if person_name and organization:
        return f"{person_name} ({organization})"
    if person_name:
        return person_name
    if organization:
        return organization
    return "Submitter name not provided"


def _stage_file(*, markdown_db_path, representation, stage_number):
    stage_directory = dict(STAGES)[stage_number]
    return Path(markdown_db_path) / stage_directory / representation["markdown_path"]


def highest_available_stage(*, markdown_db_path, representation):
    for stage_number, _directory in reversed(STAGES):
        if _stage_file(
            markdown_db_path=markdown_db_path,
            representation=representation, stage_number=stage_number,
        ).is_file():
            return stage_number
    return None


def _read_stage_text(*, markdown_db_path, representation, stage_number):
    stage_file = _stage_file(
        markdown_db_path=markdown_db_path,
        representation=representation, stage_number=stage_number,
    )
    if not stage_file.is_file():
        return None
    return stage_file.read_text(encoding="utf-8")


def _excerpt(*, text, query, context_characters=160):
    position = text.lower().find(query.lower())
    if position == -1:
        return ""
    start = max(0, position - context_characters)
    end = min(len(text), position + len(query) + context_characters)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def search_comments(*, markdown_db_path, representations, query, stage=None):
    """Brute-force case-insensitive substring search across representations."""
    normalized_query = query.strip()
    if not normalized_query:
        return []
    results = []
    for representation in representations:
        search_stage = stage or highest_available_stage(
            markdown_db_path=markdown_db_path, representation=representation,
        )
        if search_stage is None:
            continue
        text = _read_stage_text(
            markdown_db_path=markdown_db_path,
            representation=representation, stage_number=search_stage,
        )
        if text is None or normalized_query.lower() not in text.lower():
            continue
        results.append({
            "representation": representation,
            "stage": search_stage,
            "excerpt": _excerpt(text=text, query=normalized_query),
        })
    return results


def _render_page(*, title, body):
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title>"
        "<style>"
        "body{font-family:sans-serif;margin:2rem;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #ccc;padding:.5rem;text-align:left;"
        "vertical-align:top;}"
        "th{background:#f4f4f4;}"
        "pre{white-space:pre-wrap;border:1px solid #eee;padding:1rem;}"
        ".search{margin-bottom:1rem;}"
        "a{color:#00447c;}"
        "</style></head><body>"
        f"{body}"
        "</body></html>"
    )


def _search_form(*, query=""):
    return (
        '<form class="search" action="/comments/search" method="get">'
        '<label for="q">Search comments:</label> '
        f'<input id="q" name="q" type="text" value="{escape(query)}"> '
        '<button type="submit">Search</button> '
        '<a href="/comments/">All comments</a>'
        "</form>"
    )


def _representation_label(*, representation):
    if representation["logical_document_role"] == "comment_attachment":
        number = representation.get("attachment_number")
        if number is not None:
            return f"Attachment {number}"
        return "Attachment"
    return "Form comment"


def _submission_href(*, comment_id):
    return f"/comments/{escape(comment_id)}/"


def _representation_href(*, representation):
    return (
        f"/comments/{escape(representation['comment_id'])}/"
        f"representations/{escape(representation['representation_id'])}/"
    )


def _stage_href(*, representation, stage_number):
    return (
        f"/comments/{escape(representation['comment_id'])}/"
        f"representations/{escape(representation['representation_id'])}/"
        f"stage/{stage_number}/"
    )


def _render_comment_table(*, submissions):
    rows = []
    for submission in submissions:
        attachment_links = []
        for representation in submission["representations"]:
            if representation["logical_document_role"] == "comment_attachment":
                attachment_links.append(
                    f'<a href="{_representation_href(representation=representation)}">'
                    f"{escape(_representation_label(representation=representation))}</a>"
                )
        attachment_cell = ", ".join(attachment_links) if attachment_links else "—"
        withdrawn = "Withdrawn" if submission.get("withdrawn") else ""
        rows.append(
            "<tr>"
            f"<td><a href=\"{_submission_href(comment_id=submission['comment_id'])}\">"
            f"{escape(submission['comment_id'])}</a></td>"
            f"<td>{escape(display_name_for_submission(submission=submission))}</td>"
            f"<td>{escape(submission.get('organization') or '')}</td>"
            f"<td>{escape(submission.get('title') or '')}</td>"
            f"<td>{escape(submission.get('docket_id') or '')}</td>"
            f"<td>{attachment_cell}</td>"
            f"<td>{escape(withdrawn)}</td>"
            "</tr>"
        )
    return (
        '<table><thead><tr>'
        "<th>Comment ID</th><th>Author</th><th>Organization</th>"
        "<th>Title</th><th>Docket</th><th>Attachments</th><th>Status</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )

def _render_submission(*, submission, markdown_db_path):
    rows = []
    for representation in submission["representations"]:
        highest_stage = highest_available_stage(
            markdown_db_path=markdown_db_path, representation=representation,
        )
        stage_links = ", ".join(
            f'<a href="{_stage_href(representation=representation, stage_number=number)}">'
            f"{number}</a>"
            for number, _directory in STAGES
        )
        rows.append(
            "<tr>"
            f"<td>{escape(_representation_label(representation=representation))}</td>"
            f"<td>{escape(representation['source_object_key'])}</td>"
            f"<td>{escape(str(highest_stage) if highest_stage else 'none')}</td>"
            f"<td>{stage_links}</td>"
            "</tr>"
        )
    return (
        f"<h1>{escape(submission['comment_id'])}</h1>"
        f"<p><strong>Author:</strong> "
        f"{escape(display_name_for_submission(submission=submission))}</p>"
        f"<p><strong>Organization:</strong> "
        f"{escape(submission.get('organization') or '')}</p>"
        f"<p><strong>Title:</strong> {escape(submission.get('title') or '')}</p>"
        f"<p><strong>Docket:</strong> {escape(submission.get('docket_id') or '')}</p>"
        f"<p><a href=\"/comments/\">Back to all comments</a></p>"
        "<h2>Representations</h2>"
        '<table><thead><tr><th>Representation</th><th>Source object key</th>'
        "<th>Highest stage</th><th>Stages</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_representation(*, representation):
    stage_links = ", ".join(
        f'<a href="{_stage_href(representation=representation, stage_number=number)}">'
        f"{number}</a>"
        for number, _directory in STAGES
    )
    return (
        f"<h1>{escape(_representation_label(representation=representation))} — "
        f"{escape(representation['comment_id'])}</h1>"
        f"<p><strong>Source object key:</strong> "
        f"{escape(representation['source_object_key'])}</p>"
        f"<p><a href=\"{_submission_href(comment_id=representation['comment_id'])}\">"
        "Back to submission</a></p>"
        f"<h2>Stages</h2><p>{stage_links}</p>"
    )


def _render_stage(*, representation, stage_number, markdown_db_path):
    text = _read_stage_text(
        markdown_db_path=markdown_db_path,
        representation=representation, stage_number=stage_number,
    )
    if text is None:
        content = f"<p>Stage {stage_number} has not been generated for this representation.</p>"
    else:
        content = f"<pre>{escape(text)}</pre>"
    return (
        f"<h1>{escape(_representation_label(representation=representation))} — "
        f"{escape(representation['comment_id'])} — Stage {stage_number}</h1>"
        f"<p><a href=\"{_representation_href(representation=representation)}\">"
        "Back to representation</a></p>"
        + content
    )


def _find_submission(*, submissions, comment_id):
    for submission in submissions:
        if submission["comment_id"] == comment_id:
            return submission
    return None


def _find_representation(*, submissions, comment_id, representation_id):
    submission = _find_submission(submissions=submissions, comment_id=comment_id)
    if submission is None:
        return None
    for representation in submission["representations"]:
        if representation["representation_id"] == representation_id:
            return representation
    return None

    return results

class CommentBrowserHandler(BaseHTTPRequestHandler):
    server_version = "CommentBrowser/1.0"

    def _send_html(self, *, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, *, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _send_not_found(self):
        self._send_html(
            html=_render_page(
                title="Not found", body="<h1>Not found</h1>"
                '<p><a href="/comments/">Back to all comments</a></p>',
            ),
            status=404,
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        submissions = self.server.catalog.submissions
        representations = self.server.catalog.representations

        if path in ("/", ""):
            self._redirect(location="/comments/")
            return

        if path == "/comments/":
            body = (
                "<h1>Comments</h1>"
                + _search_form()
                + _render_comment_table(submissions=submissions)
            )
            self._send_html(html=_render_page(title="Comments", body=body))
            return

        if path == "/comments/search":
            query_text = (parse_qs(parsed.query).get("q", [""])[0]).strip()
            if not query_text:
                self._redirect(location="/comments/")
                return
            matches = search_comments(
                markdown_db_path=self.server.markdown_db_path,
                representations=representations, query=query_text,
            )
            if not matches:
                body = (
                    f"<h1>Search results for “{escape(query_text)}”</h1>"
                    + _search_form(query=query_text)
                    + "<p>No comments matched.</p>"
                )
            else:
                rows = []
                for match in matches:
                    representation = match["representation"]
                    rows.append(
                        "<tr>"
                        f"<td><a href=\"{_submission_href(comment_id=representation['comment_id'])}\">"
                        f"{escape(representation['comment_id'])}</a></td>"
                        f"<td>{escape(_representation_label(representation=representation))}</td>"
                        f"<td><a href=\"{_stage_href(representation=representation, stage_number=match['stage'])}\">"
                        f"Stage {match['stage']}</a></td>"
                        f"<td>{escape(match['excerpt'])}</td>"
                        "</tr>"
                    )
                body = (
                    f"<h1>Search results for “{escape(query_text)}”</h1>"
                    + _search_form(query=query_text)
                    + '<table><thead><tr><th>Comment ID</th><th>Representation</th>'
                    "<th>Match</th><th>Excerpt</th></tr></thead><tbody>"
                    + "".join(rows) + "</tbody></table>"
                )
            self._send_html(html=_render_page(title="Search", body=body))
            return
        match = re.fullmatch(
            r"/comments/([A-Za-z0-9-]+)/representations/([a-f0-9]+)/stage/(\d)/",
            path,
        )
        if match:
            comment_id, representation_id, stage_number = match.groups()
            stage_number = int(stage_number)
            representation = _find_representation(
                submissions=submissions, comment_id=comment_id,
                representation_id=representation_id,
            )
            if representation is None or stage_number not in VALID_STAGE_NUMBERS:
                self._send_not_found()
                return
            body = _search_form() + _render_stage(
                representation=representation, stage_number=stage_number,
                markdown_db_path=self.server.markdown_db_path,
            )
            self._send_html(html=_render_page(title=f"Stage {stage_number}", body=body))
            return

        match = re.fullmatch(
            r"/comments/([A-Za-z0-9-]+)/representations/([a-f0-9]+)/", path
        )
        if match:
            comment_id, representation_id = match.groups()
            representation = _find_representation(
                submissions=submissions, comment_id=comment_id,
                representation_id=representation_id,
            )
            if representation is None:
                self._send_not_found()
                return
            body = _search_form() + _render_representation(representation=representation)
            self._send_html(html=_render_page(title="Representation", body=body))
            return

        match = re.fullmatch(r"/comments/([A-Za-z0-9-]+)/", path)
        if match:
            comment_id = match.group(1)
            submission = _find_submission(submissions=submissions, comment_id=comment_id)
            if submission is None:
                self._send_not_found()
                return
            body = _search_form() + _render_submission(
                submission=submission, markdown_db_path=self.server.markdown_db_path,
            )
            self._send_html(html=_render_page(title=comment_id, body=body))
            return

        self._send_not_found()

    def log_message(self, format_string, *args):
        return


class CommentBrowserServer:
    def __init__(self, *, markdown_db_path, host="127.0.0.1", port=8765):
        representations, submissions = build_comment_catalog(
            markdown_db_path=markdown_db_path,
        )
        self.httpd = ThreadingHTTPServer((host, port), CommentBrowserHandler)
        self.httpd.catalog = type("Catalog", (), {
            "representations": representations, "submissions": submissions,
        })()
        self.httpd.markdown_db_path = Path(markdown_db_path)

    def serve_forever(self):
        self.httpd.serve_forever()
