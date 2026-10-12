"""Pair canonical Mirrulations extraction files with original attachments."""

import re
from pathlib import Path


EXTRACTED_ATTACHMENT_PATTERN = re.compile(
    r"^(?P<record_id>.+)_attachment_(?P<attachment_number>\d+)_extracted\.txt$"
)
STRUCTURAL_SUFFIX_STATUS = {
    ".pdf": "available-pdf",
    ".docx": "available-docx",
    ".png": "structure-pending-image",
    ".jpg": "structure-pending-image",
    ".jpeg": "structure-pending-image",
}


def extracted_attachment_identity(*, file_name):
    match = EXTRACTED_ATTACHMENT_PATTERN.match(file_name)
    if not match:
        return None
    return match.group("record_id"), int(match.group("attachment_number"))


def structural_attachment_identity(*, file_name):
    file_path = Path(file_name)
    suffix = file_path.suffix.lower()
    stem_match = re.match(
        r"^(?P<record_id>.+)_attachment_(?P<attachment_number>\d+)$",
        file_path.stem,
    )
    if not stem_match or suffix not in STRUCTURAL_SUFFIX_STATUS:
        return None
    return (
        stem_match.group("record_id"),
        int(stem_match.group("attachment_number")),
        suffix,
    )


def pair_extracted_attachments(*, source_root, assets):
    """Return deterministic pair records keyed by canonical object key."""
    originals_by_identity = {}
    for asset in assets:
        identity = structural_attachment_identity(
            file_name=Path(asset["source_object_key"]).name
        )
        if identity:
            originals_by_identity.setdefault(identity[:2], []).append(asset)

    pairings = {}
    for asset in assets:
        canonical_key = asset["source_object_key"]
        identity = extracted_attachment_identity(file_name=Path(canonical_key).name)
        if not identity or "/pypdf/" not in f"/{canonical_key}":
            continue
        candidates = sorted(
            originals_by_identity.get(identity, []),
            key=lambda candidate: candidate["source_object_key"],
        )
        docx_candidates = [
            candidate for candidate in candidates if candidate["source_suffix"] == ".docx"
        ]
        pdf_candidates = [
            candidate for candidate in candidates if candidate["source_suffix"] == ".pdf"
        ]
        if len(docx_candidates) == 1:
            selected = docx_candidates[0]
            status = "available-docx"
        elif len(docx_candidates) > 1:
            selected = None
            status = "ambiguous-docx"
        elif len(pdf_candidates) == 1:
            selected = pdf_candidates[0]
            status = "available-pdf"
        elif len(pdf_candidates) > 1:
            status = "ambiguous-pdf"
        elif candidates:
            status = STRUCTURAL_SUFFIX_STATUS.get(
                candidates[0]["source_suffix"], "structure-pending-unsupported"
            )
        else:
            status = "missing-original"
        pairings[canonical_key] = {
            "canonical_source_object_key": canonical_key,
            "canonical_source_sha256": asset["source_sha256"],
            "record_id": identity[0],
            "attachment_number": identity[1],
            "status": status,
            "structural_source_object_key": (
                selected["source_object_key"] if selected else None
            ),
            "structural_source_sha256": selected["source_sha256"] if selected else None,
            "structural_source_format": (
                selected["source_suffix"].lstrip(".") if selected else None
            ),
            "alternate_structural_sources": [
                {
                    "source_object_key": candidate["source_object_key"],
                    "source_sha256": candidate["source_sha256"],
                    "format": candidate["source_suffix"].lstrip("."),
                }
                for candidate in candidates
                if candidate is not selected
            ],
            "candidate_source_object_keys": [
                candidate["source_object_key"] for candidate in candidates
            ],
        }
    return pairings