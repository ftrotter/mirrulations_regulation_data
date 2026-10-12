"""Document metadata and persistent human-editable friendly-name tables."""

import json
from pathlib import Path
import re

from .resource_index import current_resource


def normalized_friendly_name(*, organization, person_name, title):
    organization = re.sub(r"\s+", " ", organization or "").strip()
    person_name = re.sub(r"\s+", " ", person_name or "").strip()
    title = re.sub(r"\s+", " ", title or "").strip()
    subject = " ".join(value for value in (organization, person_name) if value)
    if subject and title:
        return f"{subject}: {title}"
    return subject or title or "Untitled document"


def metadata_from_json(*, json_path):
    value = json.loads(json_path.read_text(encoding="utf-8"))
    data = value.get("data", {}) if isinstance(value, dict) else {}
    attributes = data.get("attributes", {}) if isinstance(data, dict) else {}
    import hashlib
    return metadata_from_resource(resource={
        "public_id": data.get("id"),
        "resource_type": data.get("type"),
        "object_id": attributes.get("objectId"),
        "source_object_key": str(json_path),
        "source_sha256": hashlib.sha256(json_path.read_bytes()).hexdigest(),
        "revision_number": 0,
        "attribute_presence": {
            field: ("explicit-null" if field_value is None else "present")
            for field, field_value in attributes.items()
        },
        "attributes": attributes,
    })


def metadata_index(*, source_root, resource_index=None):
    records = {}
    if resource_index is not None:
        public_id_counts = {}
        for _resource_type, public_id in resource_index["current_by_identity"]:
            public_id_counts[public_id] = public_id_counts.get(public_id, 0) + 1
        for (resource_type, public_id), resource in resource_index[
            "current_by_identity"
        ].items():
            metadata = metadata_from_resource(resource=resource)
            records[(resource_type, public_id)] = metadata
            if public_id_counts[public_id] == 1:
                records[public_id] = metadata
        return records
    for json_path in sorted(source_root.rglob("*.json")):
        try:
            metadata = metadata_from_json(json_path=json_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        document_id = metadata.get("document_id")
        if document_id and document_id not in records:
            records[document_id] = metadata
    return records


def metadata_from_resource(*, resource):
    attributes = resource["attributes"]
    first_name = attributes.get("firstName") or ""
    last_name = attributes.get("lastName") or ""
    person_name = " ".join(item for item in (first_name, last_name) if item).strip()
    authors = attributes.get("authors")
    if not person_name and isinstance(authors, list):
        person_name = ", ".join(str(author) for author in authors)
    return {
        "document_id": resource["public_id"],
        "api_resource_type": resource["resource_type"],
        "object_id": resource.get("object_id"),
        "agency_id": attributes.get("agencyId"),
        "docket_id": attributes.get("docketId"),
        "document_type": attributes.get("documentType"),
        "subtype": attributes.get("subtype"),
        "title": attributes.get("title"),
        "organization": attributes.get("organization"),
        "person_name": person_name or None,
        "authors": authors,
        "file_formats": attributes.get("fileFormats"),
        "comment_on_document_id": attributes.get("commentOnDocumentId"),
        "comment_on_object_id": attributes.get("commentOn"),
        "fr_document_number": attributes.get("frDocNum"),
        "withdrawn": attributes.get("withdrawn"),
        "reason_withdrawn": attributes.get("reasonWithdrawn"),
        "original_document_id": attributes.get("originalDocumentId"),
        "tracking_number": attributes.get("trackingNbr"),
        "attribute_presence": resource["attribute_presence"],
        "metadata_source_object_key": resource["source_object_key"],
        "metadata_source_sha256": resource["source_sha256"],
        "metadata_revision_number": resource["revision_number"],
        "metadata_selection_policy": "highest-revision-suffix",
    }


def record_id_from_source_key(*, source_object_key):
    match = re.search(r"([A-Z]+-\d{4}-\d+-\d{4})", Path(source_object_key).name)
    return match.group(1) if match else Path(source_object_key).stem


def document_metadata(*, asset, metadata_records, pairing=None):
    record_id = record_id_from_source_key(source_object_key=asset["source_object_key"])
    source_key = asset["source_object_key"]
    if pairing or "/comments/" in f"/{source_key}" or "comments_extracted_text" in source_key:
        expected_resource_type = "comments"
    elif "/documents/" in f"/{source_key}":
        expected_resource_type = "documents"
    elif "/docket/" in f"/{source_key}":
        expected_resource_type = "dockets"
    else:
        expected_resource_type = None
    metadata = dict(
        metadata_records.get((expected_resource_type, record_id), {})
        or metadata_records.get(record_id, {})
    )
    metadata.setdefault("document_id", record_id)
    if pairing:
        logical_document_role = "comment_attachment"
        representation_role = "derived_extraction"
    elif metadata.get("api_resource_type") == "comments":
        logical_document_role = "form_comment"
        representation_role = "metadata_json"
    elif metadata.get("api_resource_type") == "documents":
        logical_document_role = "regulatory_document"
        representation_role = (
            "html_body" if Path(source_key).suffix.lower() in {".htm", ".html"}
            else "metadata_json"
        )
    else:
        logical_document_role = "unclassified"
        representation_role = "readable_text"
    metadata["logical_document_role"] = logical_document_role
    metadata["representation_role"] = representation_role
    metadata["generated_friendly_name"] = normalized_friendly_name(
        organization=metadata.get("organization"),
        person_name=metadata.get("person_name"),
        title=metadata.get("title"),
    )
    if pairing and pairing.get("structural_source_object_key", "").endswith(".pdf"):
        attachment_number = pairing["attachment_number"]
        metadata["original_pdf_url"] = (
            f"https://downloads.regulations.gov/{record_id}/"
            f"attachment_{attachment_number}.pdf"
        )
        metadata["original_pdf_link"] = (
            f"[original pdf]({metadata['original_pdf_url']})"
        )
    else:
        metadata["original_pdf_url"] = None
        metadata["original_pdf_link"] = None
    return metadata


def _escape_cell(*, value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def parse_markdown_table_row(*, line):
    placeholder = "\u0000PIPE\u0000"
    protected_line = line.replace("\\|", placeholder)
    return [
        cell.strip().replace(placeholder, "|")
        for cell in protected_line.strip("|").split("|")
    ]


def read_document_edits(*, table_path):
    edits = {}
    if not table_path.is_file():
        return edits
    for line in table_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line or "generated_friendly_name" in line:
            continue
        cells = parse_markdown_table_row(line=line)
        if len(cells) == 3:
            edits[cells[2]] = cells[1]
    return edits


def write_document_friendly_names(*, table_path, documents):
    existing_edits = read_document_edits(table_path=table_path)
    lines = [
        "# Document Friendly Names", "",
        "| generated_friendly_name | edited_friendly_name | markdown_path |",
        "|---|---|---|",
    ]
    for document in sorted(documents, key=lambda item: item["markdown_path"]):
        path = document["markdown_path"]
        edited = existing_edits.get(path, "")
        lines.append(
            "| " + " | ".join(
                _escape_cell(value=value)
                for value in (document["generated_friendly_name"], edited, path)
            ) + " |"
        )
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        document["markdown_path"]: existing_edits.get(document["markdown_path"], "")
        or document["generated_friendly_name"]
        for document in documents
    }