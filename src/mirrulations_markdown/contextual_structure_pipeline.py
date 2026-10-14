"""Section-aware, batched Stage 3 structure discovery."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

from .analysis_segments import build_analysis_segments
from .llm_backend import BackendFactory, MagenticSegmentCaller
from .pipeline import STAGE_2, _write_json, _write_text
from .structure_pipeline import (
    STAGE_3, _configuration_hash, _render_stage_3, _submission_id,
    document_eligibility,
)


def _segment_hash(*, source_hash, segment, configuration_hash, target_registry=None):
    value = json.dumps({
        "source_hash": source_hash,
        "segment": segment,
        "configuration_hash": configuration_hash,
        "target_registry": target_registry or [],
        "task_type": "contextual-segment-v1",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _call_segment(
    *, caller, configuration, asset, segment, target_registry,
    allowed_targets_by_key, segment_hash
):
    result = asyncio.run(caller(
        model_spec=configuration.summary_model,
        document_type=asset.get("selection_reason", "document"),
        section_heading=segment["section_heading"],
        owned_block_ids=segment["owned_block_ids"],
        allowed_targets=target_registry,
        segment_blocks=segment["blocks"],
    ))
    returned_ids = [item.block_id for item in result.block_results]
    if returned_ids != segment["owned_block_ids"]:
        raise ValueError(
            "contextual_structure_pipeline.py Error: model block IDs must exactly "
            "match owned block IDs in order"
        )
    annotations = []
    for item in result.block_results:
        references = []
        for reference in item.backward_references:
            if reference.target_key not in allowed_targets_by_key:
                raise ValueError(
                    "contextual_structure_pipeline.py Error: invented target key "
                    f"{reference.target_key!r}"
                )
            references.append({
                "source_block_id": item.block_id,
                "target_key": reference.target_key,
                "target": allowed_targets_by_key[reference.target_key],
                "search_description": reference.search_description,
            })
        annotations.append({
            "block_id": item.block_id,
            "task_hash": f"{segment_hash}:{item.block_id}",
            "segment_task_hash": segment_hash,
            "task_status": "complete",
            "summary": result.section_summary or "Analyzed in its surrounding document context.",
            "backward_references": references,
            "reference_check_requested": True,
            "render_summary": False,
            "placement": "after-block",
        })
    if result.section_summary and segment["section_block_id"]:
        annotations.append({
            "block_id": segment["section_block_id"],
            "task_hash": f"{segment_hash}:{segment['section_block_id']}",
            "segment_task_hash": segment_hash,
            "task_status": "complete",
            "summary": result.section_summary,
            "backward_references": [],
            "reference_check_requested": False,
            "render_summary": True,
            "placement": "after-block",
        })
    return annotations


class ContextualStructureDiscoveryPipeline:
    @staticmethod
    def run(
        *, markdown_db_path, configuration, segment_caller=None,
        maximum_api_calls=None, requests_per_second=10.0, maximum_concurrency=10,
        progress_callback=None, maximum_owned_blocks=20,
        maximum_segment_characters=20000, unstructured_owned_blocks=10,
        source_object_keys=None,
    ):
        if requests_per_second <= 0 or maximum_concurrency < 1:
            raise ValueError(
                "contextual_structure_pipeline.py Error: rate and concurrency must be positive"
            )
        caller = segment_caller or MagenticSegmentCaller.call
        if segment_caller is None:
            BackendFactory.verify_credentials(model_specs=[configuration.summary_model])
        metadata_root = markdown_db_path / "metadata"
        block_records = [
            (path, json.loads(path.read_text(encoding="utf-8")))
            for path in (metadata_root / "blocks").glob("*.json")
        ]
        block_records.sort(key=lambda item: (
            0 if item[1].get("document_metadata", {}).get("logical_document_role")
            == "regulatory_document" else 1,
            item[1]["asset"]["source_object_key"],
        ))
        selected_keys = set(source_object_keys or [])
        attachment_submissions = {
            identifier for _path, record in block_records
            for identifier in [_submission_id(source_object_key=record["asset"]["source_object_key"])]
            if identifier and "_attachment_" in record["asset"]["source_object_key"]
        }
        configuration_hash = _configuration_hash(configuration=configuration)
        annotation_root = metadata_root / "structure_discovery" / "annotations"
        api_calls = 0
        reused_segments = 0
        completed_documents = 0
        failed_tasks = []
        last_request_at = None
        started_at = time.monotonic()
        for block_path, record in block_records:
            asset = record["asset"]
            if selected_keys and asset["source_object_key"] not in selected_keys:
                continue
            stage_2_path = markdown_db_path / STAGE_2 / asset["markdown_path"]
            if not stage_2_path.is_file():
                continue
            eligibility = document_eligibility(
                block_record=record, configuration=configuration,
                submission_has_attachment=(
                    _submission_id(source_object_key=asset["source_object_key"])
                    in attachment_submissions
                ),
            )
            sidecar_path = annotation_root / block_path.name
            existing = json.loads(sidecar_path.read_text()) if sidecar_path.is_file() else {}
            existing_by_segment = {}
            for annotation in existing.get("annotations", []):
                if annotation.get("task_status") == "complete" and annotation.get("segment_task_hash"):
                    existing_by_segment.setdefault(annotation["segment_task_hash"], []).append(annotation)
            annotations = []
            document_failed_tasks = []
            failed_segments = []
            if eligibility.eligible:
                segments = build_analysis_segments(
                    blocks=record["blocks"], maximum_owned_blocks=maximum_owned_blocks,
                    maximum_characters=maximum_segment_characters,
                    unstructured_owned_blocks=unstructured_owned_blocks,
                )
                pending = []
                for segment in segments:
                    task_hash = _segment_hash(
                        source_hash=asset["source_sha256"], segment=segment,
                        configuration_hash=configuration_hash,
                        target_registry=record.get("target_registry", []),
                    )
                    expected_ids = set(segment["owned_block_ids"])
                    if segment["section_block_id"]:
                        expected_ids.add(segment["section_block_id"])
                    cached = existing_by_segment.get(task_hash, [])
                    if expected_ids.issubset({item["block_id"] for item in cached}):
                        annotations.extend(cached)
                        reused_segments += 1
                    else:
                        pending.append((segment, task_hash))
                futures = {}
                with ThreadPoolExecutor(max_workers=maximum_concurrency) as executor:
                    for segment, task_hash in pending:
                        if maximum_api_calls is not None and api_calls >= maximum_api_calls:
                            failure = {
                                "source_object_key": asset["source_object_key"],
                                "segment_id": segment["segment_id"],
                                "error": "contextual_structure_pipeline.py Error: API budget exhausted",
                            }
                            failed_tasks.append(failure)
                            document_failed_tasks.append(failure)
                            failed_segments.append((segment, failure["error"]))
                            continue
                        if last_request_at is not None:
                            wait = 1.0 / requests_per_second - (time.monotonic() - last_request_at)
                            if wait > 0:
                                time.sleep(wait)
                        api_calls += 1
                        last_request_at = time.monotonic()
                        if progress_callback:
                            progress_callback({
                                "event": "segment_started", "api_calls": api_calls,
                                "source_object_key": asset["source_object_key"],
                                "segment_id": segment["segment_id"],
                                "owned_block_count": len(segment["owned_block_ids"]),
                            })
                        future = executor.submit(
                            _call_segment, caller=caller, configuration=configuration,
                            asset=asset, segment=segment,
                            target_registry=record.get("target_registry", []),
                            allowed_targets_by_key={
                                target["target_key"]: target
                                for target in record.get("target_registry", [])
                            }, segment_hash=task_hash,
                        )
                        futures[future] = segment
                    for future in as_completed(futures):
                        segment = futures[future]
                        try:
                            annotations.extend(future.result())
                        except Exception as error:
                            failure = {
                                "source_object_key": asset["source_object_key"],
                                "segment_id": segment["segment_id"],
                                "error": (
                                    "contextual_structure_pipeline.py Error: segment failed "
                                    f"with {type(error).__name__}"
                                ),
                            }
                            failed_tasks.append(failure)
                            document_failed_tasks.append(failure)
                            failed_segments.append((segment, failure["error"]))
                for failed_segment, error_message in failed_segments:
                    for block_id in failed_segment["owned_block_ids"]:
                        annotations.append({
                            "block_id": block_id,
                            "task_status": "problematic",
                            "summary": None,
                            "backward_references": [],
                            "reference_check_requested": False,
                            "render_summary": False,
                            "placement": "after-block",
                            "error": error_message,
                        })
                    if failed_segment.get("section_block_id"):
                        annotations.append({
                            "block_id": failed_segment["section_block_id"],
                            "task_status": "problematic",
                            "summary": None,
                            "backward_references": [],
                            "reference_check_requested": False,
                            "render_summary": False,
                            "placement": "after-block",
                            "error": error_message,
                        })
            block_order = {block["block_id"]: index for index, block in enumerate(record["blocks"])}
            annotations.sort(key=lambda item: block_order[item["block_id"]])
            _write_json(output_path=sidecar_path, value={
                "schema_version": 2, "asset": asset,
                "configuration_hash": configuration_hash,
                "eligibility": eligibility.model_dump(mode="json"),
                "target_registry": record.get("target_registry", []),
                "annotations": annotations,
            })
            _write_text(
                output_path=markdown_db_path / STAGE_3 / asset["markdown_path"],
                text=_render_stage_3(
                    stage_2_text=stage_2_path.read_text(encoding="utf-8"),
                    annotations=annotations, eligibility=eligibility,
                    configuration=configuration,
                ),
            )
            completed_documents += 1
            if progress_callback:
                progress_callback({
                    "event": "document_completed",
                    "source_object_key": asset["source_object_key"],
                    "completed_documents": completed_documents,
                    "api_calls": api_calls, "failed_task_count": len(failed_tasks),
                })
        return {
            "completed_documents": completed_documents, "api_calls": api_calls,
            "reused_segments": reused_segments,
            "failed_task_count": len(failed_tasks), "failed_tasks": failed_tasks,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
        }