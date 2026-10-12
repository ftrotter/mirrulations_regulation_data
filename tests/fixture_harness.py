"""Manifest loading and hash validation for discoverable regression cases."""

import hashlib
from pathlib import Path
import sys

import yaml


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.docx_structure import extract_docx_structure
from mirrulations_markdown.semantic_document import (
    aligned_to_semantic_blocks, html_to_semantic_blocks, render_semantic_markdown,
)
from mirrulations_markdown.text_alignment import align_structural_units


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "regression_cases"


def discover_cases():
    return sorted(FIXTURE_ROOT.glob("*/case.yaml"))


def load_case(*, manifest_path):
    value = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError(f"fixture_harness.py Error: invalid case manifest: {manifest_path}")
    return value


def file_sha256(*, file_path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def validate_case_hashes(*, manifest_path, case):
    case_root = manifest_path.parent
    source_records = [case["canonical_source"], *case.get("structural_sources", [])]
    for record in source_records:
        source_path = case_root / record["path"]
        if not source_path.is_file():
            raise AssertionError(f"Missing fixture source: {source_path}")
        actual_hash = file_sha256(file_path=source_path)
        if actual_hash != record["sha256"]:
            raise AssertionError(
                f"Fixture hash mismatch for {source_path}: {actual_hash} != {record['sha256']}"
            )


def render_case(*, manifest_path, case):
    case_root = manifest_path.parent
    canonical_path = case_root / case["canonical_source"]["path"]
    if case["case_type"] == "form_comment":
        import json
        value = json.loads(canonical_path.read_text(encoding="utf-8"))
        comment_html = value["data"]["attributes"]["comment"]
        blocks = html_to_semantic_blocks(html_text=comment_html)
    elif case["case_type"] == "synthetic":
        blocks = html_to_semantic_blocks(
            html_text=canonical_path.read_text(encoding="utf-8", errors="replace")
        )
    elif case["case_type"] == "extracted_attachment":
        docx_records = [
            record for record in case.get("structural_sources", [])
            if record["path"].lower().endswith(".docx")
        ]
        if not docx_records:
            return None, None
        structure = extract_docx_structure(
            docx_path=case_root / docx_records[0]["path"]
        )
        alignment = align_structural_units(
            canonical_text=canonical_path.read_text(encoding="utf-8", errors="replace"),
            structure=structure,
        )
        blocks = aligned_to_semantic_blocks(aligned_blocks=alignment["blocks"])
    else:
        raise ValueError(f"fixture_harness.py Error: unsupported case type: {case['case_type']}")
    return blocks, render_semantic_markdown(blocks=blocks)