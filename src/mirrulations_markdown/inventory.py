"""Inventory exact source assets and map them to Markdown paths."""

import hashlib
from pathlib import Path


MARKDOWN_SOURCE_SUFFIXES = {".htm", ".html", ".json", ".txt"}
STRUCTURE_STATUS_BY_SUFFIX = {
    ".pdf": "available-pdf",
    ".docx": "structure-pending-docx",
    ".png": "structure-pending-image",
    ".jpg": "structure-pending-image",
    ".jpeg": "structure-pending-image",
}


def sha256_file(*, file_path):
    digest = hashlib.sha256()
    with file_path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_relative_path(*, source_relative_path):
    """Retain the source path and append .md to avoid stem collisions."""
    return Path(f"{source_relative_path.as_posix()}.md")


def inventory_source(*, source_root, docket_id=None):
    assets = []
    for file_path in sorted(source_root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(source_root)
        if docket_id and docket_id not in relative_path.parts:
            continue
        file_stat = file_path.stat()
        assets.append(
            {
                "source_object_key": relative_path.as_posix(),
                "source_sha256": sha256_file(file_path=file_path),
                "size_bytes": file_stat.st_size,
                "modified_time_ns": file_stat.st_mtime_ns,
                "source_suffix": file_path.suffix.lower(),
                "source_role": (
                    "markdown-source"
                    if file_path.suffix.lower() in MARKDOWN_SOURCE_SUFFIXES
                    else "structural-source"
                ),
                "structure_status": STRUCTURE_STATUS_BY_SUFFIX.get(
                    file_path.suffix.lower(), "not-applicable"
                ),
                "markdown_path": markdown_relative_path(
                    source_relative_path=relative_path
                ).as_posix(),
            }
        )
    return assets


def inventory_fingerprint(*, assets):
    """Identify exact selected membership and bytes independently of timestamps."""
    digest = hashlib.sha256()
    for asset in assets:
        digest.update(asset["source_object_key"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(asset["source_sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()