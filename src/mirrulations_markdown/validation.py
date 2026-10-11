"""Reusable validation for source immutability and Markdown stage outputs."""

import hashlib
import json
from pathlib import Path

from .pipeline import STAGE_1, STAGE_2


def tree_hash(*, root_path):
    """Return a deterministic hash covering relative paths and file bytes."""
    digest = hashlib.sha256()
    for file_path in sorted(path for path in root_path.rglob("*") if path.is_file()):
        digest.update(file_path.relative_to(root_path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_path.read_bytes()).digest())
    return digest.hexdigest()


def capture_tree_hashes(*, source_root, markdown_db_path):
    """Capture hashes for immutable source, Stage 1, and Stage 2 trees."""
    selected_roots = {
        "source": source_root,
        "stage001": markdown_db_path / STAGE_1,
        "stage002": markdown_db_path / STAGE_2,
    }
    missing_roots = [name for name, path in selected_roots.items() if not path.is_dir()]
    if missing_roots:
        raise ValueError(
            "validation.py Error: required trees do not exist: "
            + ", ".join(missing_roots)
        )
    return {
        name: tree_hash(root_path=root_path)
        for name, root_path in selected_roots.items()
    }


def compare_tree_hashes(*, before_hashes, after_hashes):
    """Return changed tree names and raise no ambiguous generic error."""
    tree_names = sorted(set(before_hashes) | set(after_hashes))
    return [
        tree_name
        for tree_name in tree_names
        if before_hashes.get(tree_name) != after_hashes.get(tree_name)
    ]


def write_hash_snapshot(*, output_path, tree_hashes):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(tree_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_hash_snapshot(*, snapshot_path):
    if not snapshot_path.is_file():
        raise ValueError(
            f"validation.py Error: hash snapshot does not exist: {snapshot_path}"
        )
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def corpus_summary(*, markdown_db_path, primary_source_object_key=None):
    """Summarize verified run output and optionally one primary document."""
    run_status_path = markdown_db_path / "metadata" / "runs" / "latest.json"
    if not run_status_path.is_file():
        raise ValueError(
            f"validation.py Error: run status does not exist: {run_status_path}"
        )
    run_status = json.loads(run_status_path.read_text(encoding="utf-8"))
    summary = {
        "source_assets": run_status["source_asset_count"],
        "failed_assets": run_status["failed_asset_count"],
        "stage001_files": sum(
            1 for _ in (markdown_db_path / STAGE_1).rglob("*.md")
        ),
        "stage002_files": sum(
            1 for _ in (markdown_db_path / STAGE_2).rglob("*.md")
        ),
    }
    if primary_source_object_key:
        metadata_name = hashlib.sha256(
            primary_source_object_key.encode("utf-8")
        ).hexdigest()
        blocks_path = markdown_db_path / "metadata" / "blocks" / f"{metadata_name}.json"
        citations_path = (
            markdown_db_path
            / "metadata"
            / "annotations"
            / "citations"
            / f"{metadata_name}.json"
        )
        stage_1_path = markdown_db_path / STAGE_1 / f"{primary_source_object_key}.md"
        stage_2_path = markdown_db_path / STAGE_2 / f"{primary_source_object_key}.md"
        for required_path in (blocks_path, citations_path, stage_1_path, stage_2_path):
            if not required_path.is_file():
                raise ValueError(
                    f"validation.py Error: primary document artifact is missing: "
                    f"{required_path}"
                )
        blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
        citations = json.loads(citations_path.read_text(encoding="utf-8"))
        summary["primary_document"] = {
            "stage001_bytes": stage_1_path.stat().st_size,
            "stage002_bytes": stage_2_path.stat().st_size,
            "rendered_nul_bytes": stage_1_path.read_bytes().count(b"\0"),
            "removed_nul_code_points": blocks["blocks"][0]["normalization"][
                "removed_nul_code_points"
            ],
            "resolved_citations": sum(
                1
                for citation in citations["citations"]
                if citation.get("resolution_status") == "resolved"
            ),
        }
    return summary