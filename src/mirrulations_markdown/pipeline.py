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
from .docx_structure import extract_docx_structure
from .friendly_metadata import (
    document_metadata, metadata_index, write_document_friendly_names,
)
from .inventory import inventory_source
from .pdf_structure import extract_pdf_structure
from .source_pairing import pair_extracted_attachments
from .text_alignment import align_pdf_paragraphs, align_structural_units
from .semantic_document import (
    aligned_to_semantic_blocks, html_to_semantic_blocks,
    render_semantic_markdown,
)
from .reference_metadata import (
    normalized_reference_text, resolve_reference_names,
    write_reference_friendly_names,
)
from .reference_targets import build_target_registry
from .reverse_lookup import write_citation_reverse_lookup


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


def _front_matter(
    *, asset, selected_source_location, pairing=None, friendly_metadata=None
):
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
    if friendly_metadata:
        for key in (
            "title", "authors", "organization", "person_name", "document_type",
            "docket_id", "generated_friendly_name", "original_pdf_url",
            "original_pdf_link",
        ):
            values[key] = friendly_metadata.get(key)
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


def _render_blocks(*, blocks, citations_by_block=None, reference_names=None):
    def render_text(block):
        text = block["plain_text"]
        if citations_by_block is not None:
            text = render_citations(
                text=text, citations=citations_by_block.get(block["block_id"], []),
                reference_names=reference_names,
            )
        return text
    return render_semantic_markdown(blocks=blocks, text_renderer=render_text)


class MarkdownPipeline:
    """Namespace for the ordered first-milestone operations."""

    @staticmethod
    def run(
        *, source_root, markdown_db_path, docket_id=None,
        refresh_reference_titles=False, maximum_title_fetches=None,
        title_requests_per_second=1.0, title_opener=None, title_sleeper=None,
        progress_callback=None,
    ):
        assets = inventory_source(source_root=source_root, docket_id=docket_id)
        markdown_assets, selection_decisions = select_logical_documents(
            source_root=source_root, assets=assets
        )
        pairings = pair_extracted_attachments(source_root=source_root, assets=assets)
        metadata_records = metadata_index(source_root=source_root)
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
        for asset_number, asset in enumerate(markdown_assets, start=1):
            try:
                asset_adapter_results = MarkdownPipeline._process_asset(
                    source_root=source_root,
                    markdown_db_path=markdown_db_path,
                    metadata_root=metadata_root,
                    asset=asset,
                    pairing=pairings.get(asset["source_object_key"]),
                    friendly_metadata=document_metadata(
                        asset=asset, metadata_records=metadata_records,
                        pairing=pairings.get(asset["source_object_key"]),
                    ),
                    target_registry=build_target_registry(
                        source_root=source_root,
                        source_object_key=asset["source_object_key"],
                    ),
                )
                adapter_results.extend(asset_adapter_results)
                if progress_callback:
                    progress_callback({
                        "event": "asset_completed",
                        "asset_number": asset_number,
                        "asset_count": len(markdown_assets),
                        "source_object_key": asset["source_object_key"],
                        "failure_count": len(failures),
                    })
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                failures.append(
                    {
                        "source_object_key": asset["source_object_key"],
                        "error": f"pipeline.py Error: {type(error).__name__}: {error}",
                    }
                )
                if progress_callback:
                    progress_callback({
                        "event": "asset_failed",
                        "asset_number": asset_number,
                        "asset_count": len(markdown_assets),
                        "source_object_key": asset["source_object_key"],
                        "failure_count": len(failures),
                    })
        if progress_callback:
            progress_callback({
                "event": "global_metadata_started",
                "asset_count": len(markdown_assets),
            })
        title_fetch_count = MarkdownPipeline._finalize_global_metadata(
            markdown_db_path=markdown_db_path, metadata_root=metadata_root,
            refresh_reference_titles=refresh_reference_titles,
            maximum_title_fetches=maximum_title_fetches,
            title_requests_per_second=title_requests_per_second,
            title_opener=title_opener, title_sleeper=title_sleeper,
        )
        if progress_callback:
            progress_callback({
                "event": "global_metadata_completed",
                "title_fetch_count": title_fetch_count,
            })
        run_status = {
            "schema_version": 1,
            "source_asset_count": len(assets),
            "markdown_asset_count": len(markdown_assets),
            "completed_asset_count": len(markdown_assets) - len(failures),
            "failed_asset_count": len(failures),
            "failures": failures,
            "adapter_results": adapter_results,
            "title_fetch_count": title_fetch_count,
        }
        _write_json(
            output_path=metadata_root / "runs" / "latest.json", value=run_status
        )
        return run_status

    @staticmethod
    def finalize_global_metadata(
        *, markdown_db_path, refresh_reference_titles=False,
        maximum_title_fetches=None, title_requests_per_second=1.0,
        title_opener=None, title_sleeper=None,
    ):
        return MarkdownPipeline._finalize_global_metadata(
            markdown_db_path=markdown_db_path,
            metadata_root=markdown_db_path / "metadata",
            refresh_reference_titles=refresh_reference_titles,
            maximum_title_fetches=maximum_title_fetches,
            title_requests_per_second=title_requests_per_second,
            title_opener=title_opener,
            title_sleeper=title_sleeper,
        )

    @staticmethod
    def _finalize_global_metadata(
        *, markdown_db_path, metadata_root, refresh_reference_titles,
        maximum_title_fetches, title_requests_per_second, title_opener,
        title_sleeper
    ):
        documents = []
        all_citations = []
        block_records = {}
        for block_path in sorted((metadata_root / "blocks").glob("*.json")):
            record = json.loads(block_path.read_text(encoding="utf-8"))
            block_records[block_path.stem] = record
            metadata = record.get("document_metadata") or {}
            documents.append({
                "generated_friendly_name": metadata.get(
                    "generated_friendly_name", record["asset"]["source_object_key"]
                ),
                "markdown_path": record["asset"]["markdown_path"],
            })
        document_names = write_document_friendly_names(
            table_path=metadata_root / "document_friendly_names.md",
            documents=documents,
        )
        for citation_path in sorted(
            (metadata_root / "annotations" / "citations").glob("*.json")
        ):
            record = block_records.get(citation_path.stem)
            if not record:
                continue
            for citation in json.loads(citation_path.read_text(encoding="utf-8"))[
                "citations"
            ]:
                citation["markdown_path"] = record["asset"]["markdown_path"]
                all_citations.append(citation)
        unique_authorities = {}
        for citation in all_citations:
            citation["reference_text"] = (
                normalized_reference_text(
                    normalized_target=citation["normalized_target"]
                )
                if citation["citation_family"] in {"usc", "cfr"}
                else citation.get("structured_components", {}).get(
                    "corrected_citation"
                ) or citation["matched_text"]
            )
            unique_authorities.setdefault(citation["normalized_target"], citation)
        cache, fetch_count = resolve_reference_names(
            citations=list(unique_authorities.values()),
            cache_path=metadata_root / "cache" / "reference_titles.json",
            refresh=refresh_reference_titles,
            opener=title_opener,
            maximum_fetches=maximum_title_fetches,
            requests_per_second=title_requests_per_second,
            sleeper=title_sleeper,
        )
        references = []
        for target, citation in unique_authorities.items():
            cache_record = cache[target]
            references.append({
                "normalized_target": target,
                "official_reference_name": cache_record["official_reference_name"],
                "reference_text": citation["reference_text"],
                "reference_url": citation.get("destination_url") or "",
            })
        reference_names = write_reference_friendly_names(
            table_path=metadata_root / "reference_friendly_names.md",
            references=references,
        )
        for citation_path in sorted(
            (metadata_root / "annotations" / "citations").glob("*.json")
        ):
            citation_document = json.loads(citation_path.read_text(encoding="utf-8"))
            for citation in citation_document["citations"]:
                target = citation["normalized_target"]
                citation["official_reference_name"] = cache[target][
                    "official_reference_name"
                ]
                citation["friendly_reference_name"] = reference_names[target]
            _write_json(output_path=citation_path, value=citation_document)
        for metadata_name, record in block_records.items():
            citation_path = (
                metadata_root / "annotations" / "citations" / f"{metadata_name}.json"
            )
            if not citation_path.is_file():
                continue
            citations = json.loads(citation_path.read_text(encoding="utf-8"))["citations"]
            citations_by_block = {}
            for citation in citations:
                citations_by_block.setdefault(citation["block_id"], []).append(citation)
            asset = record["asset"]
            selected_location = (
                "$html" if asset["source_suffix"] in {".htm", ".html"}
                else asset.get("content_location") or "$text"
            )
            stage_2_text = _front_matter(
                asset=asset, selected_source_location=selected_location,
                pairing=record.get("pairing"),
                friendly_metadata=record.get("document_metadata"),
            ) + _render_blocks(
                blocks=record["blocks"], citations_by_block=citations_by_block,
                reference_names=reference_names,
            )
            _write_text(
                output_path=markdown_db_path / STAGE_2 / asset["markdown_path"],
                text=stage_2_text,
            )
        write_citation_reverse_lookup(
            output_path=metadata_root / "citation_reverse_lookup.md",
            citations=all_citations, reference_names=reference_names,
            document_names=document_names,
        )
        return fetch_count

    @staticmethod
    def _process_asset(
        *, source_root, markdown_db_path, metadata_root, asset, pairing=None,
        friendly_metadata=None, target_registry=None
    ):
        source_path = source_root / asset["source_object_key"]
        markdown_body, selected_source_location, normalization = _convert_asset(
            source_path=source_path, source_suffix=asset["source_suffix"]
        )
        alignment = None
        blocks = None
        if (
            asset["source_suffix"] == ".json"
            and asset.get("content_location") == "data.attributes.comment"
        ):
            source_json = json.loads(source_path.read_text(encoding="utf-8"))
            comment_html = source_json["data"]["attributes"]["comment"]
            blocks = html_to_semantic_blocks(html_text=comment_html)
            for block in blocks:
                block["normalization"] = normalization
        elif pairing and pairing["status"] in {"available-docx", "available-pdf"}:
            canonical_text = source_path.read_text(encoding="utf-8", errors="replace")
            structural_path = source_root / pairing["structural_source_object_key"]
            if pairing["status"] == "available-docx":
                docx_structure = extract_docx_structure(docx_path=structural_path)
                alignment = align_structural_units(
                    canonical_text=canonical_text, structure=docx_structure
                )
            else:
                pdf_structure = extract_pdf_structure(pdf_path=structural_path)
                alignment = align_pdf_paragraphs(
                    canonical_text=canonical_text, pdf_structure=pdf_structure
                )
        if alignment and alignment["blocks"]:
            blocks = aligned_to_semantic_blocks(
                aligned_blocks=alignment["blocks"]
            )
            for block in blocks:
                block["normalization"] = normalization
        elif blocks is None:
            blocks = [_content_block(
                markdown_body=markdown_body, normalization=normalization
            )]
        document_version = asset["source_sha256"]
        stage_1_text = (
            _front_matter(
                asset=asset,
                selected_source_location=selected_source_location,
                pairing=pairing,
                friendly_metadata=friendly_metadata,
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
                friendly_metadata=friendly_metadata,
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
                "document_metadata": friendly_metadata,
                "target_registry": target_registry or [],
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