"""Deterministic initial-Markdown and citation-enrichment pipeline."""

import hashlib
import json
from pathlib import Path

from .citations import (
    external_adapter_statuses,
    extract_eyecite_citations,
    extract_explicit_citations,
    reconcile_candidates,
    render_citations,
    resolve_candidate,
)
from .conversion import html_to_markdown, json_to_markdown, text_to_markdown
from .document_selection import select_logical_documents
from .inventory import inventory_source
from .pdf_structure import extract_pdf_structure
from .source_pairing import pair_extracted_attachments
from .text_alignment import align_pdf_paragraphs


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


def _metadata_name(*, source_object_key):
    return hashlib.sha256(source_object_key.encode("utf-8")).hexdigest()


def _prune_stale_outputs(*, markdown_db_path, metadata_root, selected_assets):
    """Remove only generated artifacts no longer selected by the current run."""
    selected_markdown_paths = {
        asset["markdown_path"] for asset in selected_assets
    }
    for stage_name in (STAGE_1, STAGE_2):
        stage_root = markdown_db_path / stage_name
        if not stage_root.is_dir():
            continue
        for markdown_path in stage_root.rglob("*.md"):
            relative_path = markdown_path.relative_to(stage_root).as_posix()
            if relative_path not in selected_markdown_paths:
                markdown_path.unlink()
    selected_metadata_names = {
        _metadata_name(source_object_key=asset["source_object_key"])
        for asset in selected_assets
    }
    sidecar_roots = (
        metadata_root / "blocks",
        metadata_root / "annotations" / "citation_candidates",
        metadata_root / "annotations" / "citations",
    )
    for sidecar_root in sidecar_roots:
        if not sidecar_root.is_dir():
            continue
        for sidecar_path in sidecar_root.glob("*.json"):
            if sidecar_path.stem not in selected_metadata_names:
                sidecar_path.unlink()


def _front_matter(*, asset, selected_source_location, pairing=None):
    values = {
        "document_id": Path(asset["source_object_key"]).stem,
        "source_object_key": asset["source_object_key"],
        "source_sha256": asset["source_sha256"],
        "source_version": f"sha256:{asset['source_sha256']}",
        "selected_source_location": selected_source_location,
    }
    if pairing and pairing.get("structural_source_object_key"):
        values["structural_source_object_key"] = pairing["structural_source_object_key"]
        values["structural_source_sha256"] = pairing["structural_source_sha256"]
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


def _render_blocks(*, blocks, citations_by_block=None):
    parts = []
    for block in blocks:
        text = block["plain_text"]
        if citations_by_block is not None:
            text = render_citations(
                text=text, citations=citations_by_block.get(block["block_id"], [])
            )
        if block["block_type"] == "heading":
            text = f"## {text}"
        parts.append(f'<a id="{block["block_id"]}"></a>\n\n{text}')
    return "\n\n".join(parts) + "\n"


class MarkdownPipeline:
    """Namespace for the ordered first-milestone operations."""

    @staticmethod
    def run(*, source_root, markdown_db_path, docket_id=None):
        assets = inventory_source(source_root=source_root, docket_id=docket_id)
        markdown_assets, selection_decisions = select_logical_documents(
            source_root=source_root, assets=assets
        )
        pairings = pair_extracted_attachments(source_root=source_root, assets=assets)
        metadata_root = markdown_db_path / "metadata"
        _write_json(
            output_path=metadata_root / "manifests" / "source_inventory.json",
            value={"schema_version": 1, "assets": assets},
        )
        _write_json(
            output_path=metadata_root / "manifests" / "document_selection.json",
            value={"schema_version": 1, "decisions": selection_decisions},
        )
        _prune_stale_outputs(
            markdown_db_path=markdown_db_path,
            metadata_root=metadata_root,
            selected_assets=markdown_assets,
        )
        _write_json(
            output_path=metadata_root / "manifests" / "source_pairings.json",
            value={"schema_version": 1, "pairings": list(pairings.values())},
        )
        adapter_statuses = external_adapter_statuses()
        _write_json(
            output_path=metadata_root / "runs" / "adapter_status.json",
            value={"schema_version": 1, "adapters": adapter_statuses},
        )
        failures = []
        adapter_results = []
        for asset in markdown_assets:
            try:
                asset_adapter_results = MarkdownPipeline._process_asset(
                    source_root=source_root,
                    markdown_db_path=markdown_db_path,
                    metadata_root=metadata_root,
                    asset=asset,
                    pairing=pairings.get(asset["source_object_key"]),
                )
                adapter_results.extend(asset_adapter_results)
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
            "markdown_asset_count": len(markdown_assets),
            "completed_asset_count": len(markdown_assets) - len(failures),
            "failed_asset_count": len(failures),
            "failures": failures,
            "adapter_results": adapter_results,
        }
        _write_json(
            output_path=metadata_root / "runs" / "latest.json", value=run_status
        )
        return run_status

    @staticmethod
    def _process_asset(
        *, source_root, markdown_db_path, metadata_root, asset, pairing=None
    ):
        source_path = source_root / asset["source_object_key"]
        markdown_body, selected_source_location, normalization = _convert_asset(
            source_path=source_path, source_suffix=asset["source_suffix"]
        )
        alignment = None
        if pairing and pairing["status"] == "available-pdf":
            canonical_text = source_path.read_text(encoding="utf-8", errors="replace")
            pdf_structure = extract_pdf_structure(
                pdf_path=source_root / pairing["structural_source_object_key"]
            )
            alignment = align_pdf_paragraphs(
                canonical_text=canonical_text, pdf_structure=pdf_structure
            )
        if alignment and alignment["blocks"]:
            blocks = alignment["blocks"]
            for order, block in enumerate(blocks, start=1):
                block["block_id"] = f"p-{order:04d}"
                block["order"] = order
                block["heading_context"] = []
                block["normalization"] = normalization
        else:
            blocks = [_content_block(
                markdown_body=markdown_body, normalization=normalization
            )]
        document_version = asset["source_sha256"]
        stage_1_text = (
            _front_matter(
                asset=asset,
                selected_source_location=selected_source_location,
                pairing=pairing,
            )
            + _render_blocks(blocks=blocks)
        )
        stage_1_path = markdown_db_path / STAGE_1 / asset["markdown_path"]
        _write_text(output_path=stage_1_path, text=stage_1_text)

        candidates = []
        adapter_results = []
        for block in blocks:
            candidates.extend(extract_explicit_citations(
                text=block["plain_text"], document_version=document_version,
                block_id=block["block_id"],
            ))
            eyecite_candidates, eyecite_status = extract_eyecite_citations(
                text=block["plain_text"], document_version=document_version,
                block_id=block["block_id"],
            )
            candidates.extend(eyecite_candidates)
            adapter_results.append(
                {"source_object_key": asset["source_object_key"],
                 "block_id": block["block_id"], **eyecite_status}
            )
        reconciled_candidates = reconcile_candidates(candidates=candidates)
        citations = [
            resolve_candidate(candidate=candidate)
            for candidate in reconciled_candidates
        ]
        citations_by_block = {}
        for citation in citations:
            citations_by_block.setdefault(citation["block_id"], []).append(citation)
        stage_2_text = (
            _front_matter(
                asset=asset,
                selected_source_location=selected_source_location,
                pairing=pairing,
            )
            + _render_blocks(blocks=blocks, citations_by_block=citations_by_block)
        )
        stage_2_path = markdown_db_path / STAGE_2 / asset["markdown_path"]
        _write_text(output_path=stage_2_path, text=stage_2_text)

        metadata_name = _metadata_name(
            source_object_key=asset["source_object_key"]
        )
        _write_json(
            output_path=metadata_root / "blocks" / f"{metadata_name}.json",
            value={
                "schema_version": 1,
                "asset": asset,
                "pairing": pairing,
                "alignment": alignment,
                "blocks": blocks,
            },
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
        return adapter_results