"""Build allowed backward-reference target scopes from regulatory metadata."""

import json
from pathlib import Path
import re


RULE_IDENTIFIER_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d{4}-[A-Z0-9-]+)\b")
SUBMISSION_IDENTIFIER_PATTERN = re.compile(r"([A-Z]+-\d{4}-\d+-\d{4})")


def _json_metadata(*, json_path):
    value = json.loads(json_path.read_text(encoding="utf-8"))
    data = value.get("data", {})
    attributes = data.get("attributes", {})
    return data, attributes


def _agency_rule_identifier(*, document_id, metadata, source_root):
    candidates = [
        metadata.get("title") or "",
        metadata.get("regWriterInstruction") or "",
    ]
    document_directory = next(
        (
            path.parent
            for path in source_root.rglob(f"{document_id}.json")
            if "/documents/" in f"/{path.as_posix()}"
        ),
        None,
    )
    if document_directory:
        for content_path in sorted(document_directory.glob(f"{document_id}_content.htm*")):
            candidates.append(content_path.read_text(encoding="utf-8", errors="replace")[:20000])
    for candidate in candidates:
        for match in RULE_IDENTIFIER_PATTERN.finditer(candidate):
            identifier = match.group(1)
            if identifier != document_id and not re.match(r"^[A-Z]+-\d{4}-\d+$", identifier):
                return identifier
    return None


def build_target_registry(*, source_root, source_object_key):
    """Return finite allowed targets for the current source document."""
    source_path = source_root / source_object_key
    metadata_path = source_path if source_path.suffix.lower() == ".json" else None
    if metadata_path is None:
        submission_match = SUBMISSION_IDENTIFIER_PATTERN.search(source_path.name)
        if submission_match:
            submission_id = submission_match.group(1)
            metadata_path = next(
                (
                    path
                    for path in source_root.rglob(f"{submission_id}.json")
                    if "/comments/" in f"/{path.as_posix()}"
                ),
                None,
            )
    if metadata_path is None or not metadata_path.is_file():
        return []
    _data, attributes = _json_metadata(json_path=metadata_path)
    comment_on_document_id = attributes.get("commentOnDocumentId")
    docket_id = attributes.get("docketId")
    if not comment_on_document_id:
        return []
    target_metadata_path = next(
        iter(source_root.rglob(f"{comment_on_document_id}.json")), None
    )
    target_attributes = {}
    if target_metadata_path:
        _target_data, target_attributes = _json_metadata(
            json_path=target_metadata_path
        )
    rule_identifier = _agency_rule_identifier(
        document_id=comment_on_document_id,
        metadata=target_attributes,
        source_root=source_root,
    )
    document_type = target_attributes.get("documentType") or "Regulatory Document"
    type_label = document_type.lower()
    identifier_label = rule_identifier or comment_on_document_id
    scope_label = (
        f"this {type_label} {identifier_label} "
        f"(Regulations.gov document {comment_on_document_id})"
    )
    return [
        {
            "target_key": f"document:{comment_on_document_id}",
            "scope_type": "specific_document",
            "docket_id": docket_id,
            "document_ids": [comment_on_document_id],
            "document_type": document_type,
            "agency_rule_identifier": rule_identifier,
            "title": target_attributes.get("title"),
            "scope_label": scope_label,
        }
    ]