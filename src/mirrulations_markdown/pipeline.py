"""Deterministic initial-Markdown and citation-enrichment pipeline."""

import hashlib
import json
from pathlib import Path

from .citations import (
    external_adapter_statuses,
    extract_explicit_citations,
    render_citations,
    resolve_candidate,
)
from .conversion import html_to_markdown, json_to_markdown, text_to_markdown
from .inventory import inventory_source


STAGE_1 = "stage001_initial_markdown_mirror"
STAGE_2 = "stage002_addition_of_citations"


def _write_json(*, output_path, value):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def _write_text(*, output_path, text):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(output_path)


def _front_matter(*, asset, selected_source_location):
    values = {
        "document_id": Path(asset["source_object_key"]).stem,
        "source_object_key": asset["source_object_key"],
        "source_sha256": asset["source_sha256"],
        "source_version": f"sha256:{asset['source_sha256']}",
        "selected_source_location": selected_source_location,
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items())
    lines.extend(("---", ""))
    return "\n".join(lines)


def _convert_asset(*, source_path, source_suffix):
    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    if source_suffix in {".htm", ".html"}:
        markdown_body = html_to_markdown(html_text=source_text)
        selected_source_location = "$html"
    elif source_suffix == ".json":
        markdown_body, selected_source_location = json_to_markdown(
            json_text=source_text
        )
    else:
        markdown_body = text_to_markdown(text=source_text)
        selected_source_location = "$text"
    normalization = {"removed_nul_code_points": source_text.count("\x00")}
    return markdown_body, selected_source_location, normalization


def _content_block(*, markdown_body, normalization):
    plain_text = markdown_body.strip()
    return {
        "block_id": "p-0001",
        "block_type": "document",
        "order": 1,
        "plain_text": plain_text,
        "heading_context": [],
        "normalization": normalization,
    }


class MarkdownPipeline:
    """Namespace for the ordered first-milestone operations."""

    @staticmethod
    def run(*, source_root, markdown_db_path, docket_id=None):
        assets = inventory_source(source_root=source_root, docket_id=docket_id)
        metadata_root = markdown_db_path / "metadata"
        _write_json(
            output_path=metadata_root / "manifests" / "source_inventory.json",
            value={"schema_version": 1, "assets": assets},
        )
        adapter_statuses = external_adapter_statuses()
        _write_json(
            output_path=metadata_root / "runs" / "adapter_status.json",
            value={"schema_version": 1, "adapters": adapter_statuses},
        )
        failures = []
        for asset in assets:
            try:
                MarkdownPipeline._process_asset(
                    source_root=source_root,
                    markdown_db_path=markdown_db_path,
                    metadata_root=metadata_root,
                    asset=asset,
                )
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                failures.append(
                    {
                        "source_object_key": asset["source_object_key"],
                        "error": f"pipeline.py Error: {type(error).__name__}: {error}",
                    }
                )
        run_status = {
            "schema_version": 1,
            "source_asset_count": len(assets),
            "completed_asset_count": len(assets) - len(failures),
            "failed_asset_count": len(failures),
            "failures": failures,
        }
        _write_json(
            output_path=metadata_root / "runs" / "latest.json", value=run_status
        )
        return run_status

    @staticmethod
    def _process_asset(*, source_root, markdown_db_path, metadata_root, asset):
        source_path = source_root / asset["source_object_key"]
        markdown_body, selected_source_location, normalization = _convert_asset(
            source_path=source_path, source_suffix=asset["source_suffix"]
        )
        block = _content_block(
            markdown_body=markdown_body, normalization=normalization
        )
        document_version = asset["source_sha256"]
        stage_1_text = (
            _front_matter(
                asset=asset, selected_source_location=selected_source_location
            )
            + '<a id="p-0001"></a>\n\n'
            + markdown_body
        )
        stage_1_path = markdown_db_path / STAGE_1 / asset["markdown_path"]
        _write_text(output_path=stage_1_path, text=stage_1_text)

        candidates = extract_explicit_citations(
            text=block["plain_text"],
            document_version=document_version,
            block_id=block["block_id"],
        )
        citations = [resolve_candidate(candidate=candidate) for candidate in candidates]
        stage_2_body = render_citations(text=block["plain_text"], citations=citations)
        stage_2_text = (
            _front_matter(
                asset=asset, selected_source_location=selected_source_location
            )
            + '<a id="p-0001"></a>\n\n'
            + stage_2_body
            + "\n"
        )
        stage_2_path = markdown_db_path / STAGE_2 / asset["markdown_path"]
        _write_text(output_path=stage_2_path, text=stage_2_text)

        metadata_name = hashlib.sha256(
            asset["source_object_key"].encode("utf-8")
        ).hexdigest()
        _write_json(
            output_path=metadata_root / "blocks" / f"{metadata_name}.json",
            value={"schema_version": 1, "asset": asset, "blocks": [block]},
        )
        _write_json(
            output_path=metadata_root
            / "annotations"
            / "citation_candidates"
            / f"{metadata_name}.json",
            value={"schema_version": 1, "candidates": candidates},
        )
        _write_json(
            output_path=metadata_root
            / "annotations"
            / "citations"
            / f"{metadata_name}.json",
            value={"schema_version": 1, "citations": citations},
        )