"""Resolve Stage 3 backward references to exact regulatory-action blocks."""

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import time
from datetime import datetime, timezone

from .llm_backend import BackendFactory, MagenticLinkAssessor
from .pipeline import STAGE_2, _write_json, _write_text


STAGE_3 = "stage003_structure_discovery"
STAGE_4 = "stage004_backward_reference_links"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
}


def _tokens(*, text):
    return [
        token.lower() for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS and len(token) > 1
    ]


def rank_target_blocks(*, query_text, target_blocks, candidate_limit=8):
    """Return deterministic BM25-ranked substantive target blocks."""
    searchable = [
        block for block in target_blocks
        if block["block_type"] in {"section", "paragraph", "list", "quotation", "table"}
        and block["plain_text"].strip()
    ]
    document_tokens = [_tokens(text=block["plain_text"]) for block in searchable]
    document_count = len(searchable)
    if not document_count:
        return []
    query_tokens = set(_tokens(text=query_text))
    document_frequency = Counter(
        token for tokens in document_tokens for token in set(tokens)
    )
    average_length = sum(map(len, document_tokens)) / document_count or 1
    ranked = []
    for block, tokens in zip(searchable, document_tokens):
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (document_count - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * len(tokens) / average_length
            )
            score += inverse_frequency * frequency * 2.5 / denominator
        if score > 0:
            ranked.append((score, block))
    ranked.sort(key=lambda item: (-item[0], item[1]["order"]))
    return [
        {
            "block_id": block["block_id"],
            "block_type": block["block_type"],
            "heading_context": block.get("heading_context", []),
            "plain_text": block["plain_text"],
            "retrieval_score": round(score, 6),
        }
        for score, block in ranked[:candidate_limit]
    ]


def _target_record(*, block_records, document_id):
    matches = [
        (path, record) for path, record in block_records
        if document_id in Path(record["asset"]["source_object_key"]).name
        and "/documents/" in f"/{record['asset']['source_object_key']}"
    ]
    if len(matches) != 1:
        raise ValueError(
            "reference_linker.py Error: expected one semantic target document "
            f"for {document_id}, found {len(matches)}"
        )
    return matches[0]


def _link_hash(*, source_hash, source_block_id, target_key, search_description):
    value = f"{source_hash}|{source_block_id}|{target_key}|{search_description}|linker-v2"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _assess_reference(
    *, assessor, model_spec, markdown_db_path, document_id, target_record,
    source_block_text, reference, link_hash, candidates,
):
    retryable_statuses = {429, 500, 502, 503}
    assessment = None
    for attempt in range(5):
        try:
            assessment = asyncio.run(assessor(
                model_spec=model_spec,
                source_text=source_block_text,
                search_description=reference["search_description"],
                candidate_blocks=candidates,
            ))
            break
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            if status_code not in retryable_statuses or attempt == 4:
                raise
            time.sleep(2 ** attempt)
    candidate_by_id = {item["block_id"]: item for item in candidates}
    invented = set(assessment.target_block_ids) - set(candidate_by_id)
    if invented:
        raise ValueError(
            "reference_linker.py Error: assessor returned non-candidate "
            + ", ".join(sorted(invented))
        )
    targets = [{
        "target_document_id": document_id,
        "target_block_id": block_id,
        "retrieval_score": candidate_by_id[block_id]["retrieval_score"],
        "stage_2_path": str(
            markdown_db_path / STAGE_2 / target_record["asset"]["markdown_path"]
        ),
    } for block_id in assessment.target_block_ids]
    status = "linked" if targets else "no-match"
    return {
        "link_hash": link_hash,
        "status": status,
        "source_block_id": reference["source_block_id"],
        "target_key": reference["target_key"],
        "search_description": reference["search_description"],
        "confidence": assessment.confidence,
        "rationale": assessment.rationale,
        "candidate_block_ids": list(candidate_by_id),
        "targets": targets,
    }


def _render_stage_4(*, stage_3_text, links, source_markdown_path):
    rendered = stage_3_text
    links_by_source = {}
    for link in links:
        if link["status"] == "linked":
            links_by_source.setdefault(link["source_block_id"], []).append(link)
    anchor_pattern = re.compile(
        r'<a id="(?P<block_id>(?:section|paragraph|list|quotation|label|table)-\d{4})"></a>'
    )
    matches = list(anchor_pattern.finditer(rendered))
    for match in reversed(matches):
        source_links = links_by_source.get(match.group("block_id"), [])
        if not source_links:
            continue
        next_match = next(
            (candidate for candidate in matches if candidate.start() > match.start()), None
        )
        block_end = next_match.start() if next_match else len(rendered)
        lines = []
        for link in source_links:
            for target in link["targets"]:
                relative_target = Path(
                    __import__("os").path.relpath(
                        target["stage_2_path"], start=Path(source_markdown_path).parent
                    )
                ).as_posix()
                lines.append(
                    f"> **Linked regulatory-action passage:** "
                    f"[{target['target_block_id']}]({relative_target}#{target['target_block_id']})"
                )
        insertion = "\n" + "\n>\n".join(lines) + "\n\n"
        rendered = rendered[:block_end].rstrip() + insertion + rendered[block_end:]
    return rendered


class ReferenceLinkerPipeline:
    @staticmethod
    def run(
        *, markdown_db_path, model_spec, assessor=None, source_object_keys=None,
        maximum_api_calls=None, candidate_limit=12, progress_callback=None,
        modified_after=None, maximum_concurrency=1, requests_per_second=1.0,
    ):
        if requests_per_second <= 0 or maximum_concurrency < 1:
            raise ValueError(
                "reference_linker.py Error: rate and concurrency must be positive"
            )
        selected_assessor = assessor or MagenticLinkAssessor.call
        if assessor is None:
            BackendFactory.verify_credentials(model_specs=[model_spec])
        block_records = [
            (path, json.loads(path.read_text(encoding="utf-8")))
            for path in (markdown_db_path / "metadata" / "blocks").glob("*.json")
        ]
        block_by_name = {path.name: record for path, record in block_records}
        annotation_root = markdown_db_path / "metadata" / "structure_discovery" / "annotations"
        link_root = markdown_db_path / "metadata" / "reference_links"
        api_calls = 0
        linked_references = 0
        no_match_references = 0
        failed_references = []
        completed_documents = 0
        selected_keys = set(source_object_keys or [])
        last_request_at = None
        for annotation_path in sorted(annotation_root.glob("*.json")):
            if modified_after is not None:
                modification_time = datetime.fromtimestamp(
                    annotation_path.stat().st_mtime, tz=timezone.utc
                )
                if modification_time <= modified_after:
                    continue
            stage_3_record = json.loads(annotation_path.read_text(encoding="utf-8"))
            asset = stage_3_record["asset"]
            if selected_keys and asset["source_object_key"] not in selected_keys:
                continue
            source_record = block_by_name[annotation_path.name]
            source_blocks = {
                block["block_id"]: block for block in source_record["blocks"]
            }
            link_sidecar_path = link_root / annotation_path.name
            existing_links = {}
            if link_sidecar_path.is_file():
                existing_links = {
                    link["link_hash"]: link
                    for link in json.loads(
                        link_sidecar_path.read_text(encoding="utf-8")
                    ).get("links", [])
                    if link.get("status") in {"linked", "no-match"}
                    and "link_hash" in link
                }
            ordered = []
            pending = []
            for annotation in stage_3_record.get("annotations", []):
                for reference in annotation.get("backward_references", []):
                    link_hash = _link_hash(
                        source_hash=asset["source_sha256"],
                        source_block_id=reference["source_block_id"],
                        target_key=reference["target_key"],
                        search_description=reference["search_description"],
                    )
                    document_id = reference["target"]["document_ids"][0]
                    if link_hash in existing_links:
                        ordered.append({"existing": existing_links[link_hash]})
                        continue
                    _target_path, target_record = _target_record(
                        block_records=block_records, document_id=document_id
                    )
                    candidates = rank_target_blocks(
                        query_text=reference["search_description"],
                        target_blocks=target_record["blocks"],
                        candidate_limit=candidate_limit,
                    )
                    work = {
                        "link_hash": link_hash,
                        "reference": reference,
                        "document_id": document_id,
                        "target_record": target_record,
                        "candidates": candidates,
                        "source_text": source_blocks[reference["source_block_id"]]["plain_text"],
                    }
                    ordered.append({"existing": None, "work": work})
                    pending.append(work)
            results_by_hash = {}
            futures = {}
            with ThreadPoolExecutor(max_workers=maximum_concurrency) as executor:
                for work in pending:
                    if maximum_api_calls is not None and api_calls >= maximum_api_calls:
                        error_message = (
                            "reference_linker.py Error: API call budget exhausted"
                        )
                        failed_references.append({
                            "link_hash": work["link_hash"],
                            "source_object_key": asset["source_object_key"],
                            "source_block_id": work["reference"]["source_block_id"],
                            "error": error_message,
                        })
                        results_by_hash[work["link_hash"]] = {
                            "link_hash": work["link_hash"],
                            "status": "problematic",
                            "source_block_id": work["reference"]["source_block_id"],
                            "target_key": work["reference"]["target_key"],
                            "search_description": work["reference"]["search_description"],
                            "confidence": None,
                            "rationale": error_message,
                            "candidate_block_ids": [],
                            "targets": [],
                        }
                        continue
                    if last_request_at is not None:
                        wait = 1.0 / requests_per_second - (time.monotonic() - last_request_at)
                        if wait > 0:
                            time.sleep(wait)
                    api_calls += 1
                    last_request_at = time.monotonic()
                    future = executor.submit(
                        _assess_reference,
                        assessor=selected_assessor, model_spec=model_spec,
                        markdown_db_path=markdown_db_path,
                        document_id=work["document_id"],
                        target_record=work["target_record"],
                        source_block_text=work["source_text"],
                        reference=work["reference"],
                        link_hash=work["link_hash"],
                        candidates=work["candidates"],
                    )
                    futures[future] = work
                for future in as_completed(futures):
                    work = futures[future]
                    try:
                        results_by_hash[work["link_hash"]] = future.result()
                    except Exception as error:
                        status_code = getattr(error, "status_code", None)
                        suffix = f":{status_code}" if status_code is not None else ""
                        error_message = (
                            f"reference_linker.py Error: {type(error).__name__}{suffix}"
                        )
                        failed_references.append({
                            "link_hash": work["link_hash"],
                            "source_object_key": asset["source_object_key"],
                            "source_block_id": work["reference"]["source_block_id"],
                            "error": error_message,
                        })
                        results_by_hash[work["link_hash"]] = {
                            "link_hash": work["link_hash"],
                            "status": "problematic",
                            "source_block_id": work["reference"]["source_block_id"],
                            "target_key": work["reference"]["target_key"],
                            "search_description": work["reference"]["search_description"],
                            "confidence": None,
                            "rationale": error_message,
                            "candidate_block_ids": [],
                            "targets": [],
                        }
            links = []
            for item in ordered:
                if item["existing"] is not None:
                    link_record = item["existing"]
                else:
                    link_record = results_by_hash.get(item["work"]["link_hash"])
                if link_record is None:
                    continue
                links.append(link_record)
                if link_record["status"] == "linked":
                    linked_references += 1
                else:
                    no_match_references += 1
            _write_json(
                output_path=link_sidecar_path,
                value={"schema_version": 1, "asset": asset, "links": links},
            )
            stage_3_path = markdown_db_path / STAGE_3 / asset["markdown_path"]
            if stage_3_path.is_file():
                stage_4_path = markdown_db_path / STAGE_4 / asset["markdown_path"]
                _write_text(
                    output_path=stage_4_path,
                    text=_render_stage_4(
                        stage_3_text=stage_3_path.read_text(encoding="utf-8"),
                        links=links, source_markdown_path=stage_4_path,
                    ),
                )
            completed_documents += 1
            if progress_callback:
                progress_callback({
                    "event": "document_completed",
                    "source_object_key": asset["source_object_key"],
                    "api_calls": api_calls,
                })
        return {
            "completed_documents": completed_documents,
            "api_calls": api_calls,
            "linked_references": linked_references,
            "no_match_references": no_match_references,
            "failed_reference_count": len(failed_references),
            "failed_references": failed_references,
        }