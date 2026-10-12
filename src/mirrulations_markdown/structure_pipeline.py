"""Stage 3 summaries and backward-reference descriptions."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import time

from .llm_backend import BackendFactory, MagenticPassageCaller
from .pipeline import STAGE_2, _write_json, _write_text
from .structure_models import DocumentEligibility


STAGE_3 = "stage003_structure_discovery"


ATTACHMENT_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:please\s+)?see\s+(?:the\s+)?attached\b.{0,190}$",
    re.IGNORECASE,
)
ADMINISTRATIVE_REFERENCE_PATTERN = re.compile(
    r"^(?:"
    r"attention\s*:|"
    r"docket(?:\s+id)?\s*:|"
    r"re\s*:|"
    r"reference\s*:|"
    r"subject\s*:|"
    r"dear\s+(?:administrator|secretary|sir|madam|to whom)|"
    r"respectfully(?:\s+submitted)?\s*,?$|"
    r"sincerely\s*,?$"
    r")",
    re.IGNORECASE,
)


def is_attachment_placeholder(*, text):
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if len(normalized_text) > 220:
        return False
    return bool(ATTACHMENT_PLACEHOLDER_PATTERN.fullmatch(normalized_text))


def reference_detection_eligible(*, block):
    """Exclude administrative text that cannot identify a substantive provision."""
    if block["block_type"] not in {"paragraph", "list", "quotation", "table"}:
        return False
    normalized_text = re.sub(r"\s+", " ", block["plain_text"]).strip()
    if not normalized_text or ADMINISTRATIVE_REFERENCE_PATTERN.match(normalized_text):
        return False
    return True


def _submission_id(*, source_object_key):
    match = re.search(r"([A-Z]+-\d{4}-\d+-\d{4})", source_object_key)
    return match.group(1) if match else None


def _configuration_hash(*, configuration):
    serialized = json.dumps(
        configuration.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def document_eligibility(
    *, block_record, configuration, submission_has_attachment=False
):
    source_key = block_record["asset"]["source_object_key"]
    is_comment = "/comments/" in source_key or "comments_extracted_text" in source_key
    character_count = sum(len(block["plain_text"]) for block in block_record["blocks"])
    if (
        block_record["asset"].get("selection_reason")
        == "form-submitted-comment-body"
        and submission_has_attachment
        and is_attachment_placeholder(
            text=" ".join(block["plain_text"] for block in block_record["blocks"])
        )
    ):
        return DocumentEligibility(
            eligible=False, page_count=None,
            page_count_method="not-applicable-placeholder",
            character_count=character_count, maximum_comment_pages=None,
            exclusion_reason="excluded-attachment-placeholder",
        )
    if not is_comment:
        return DocumentEligibility(
            eligible=True, page_count=None, page_count_method="not-applicable",
            character_count=character_count, maximum_comment_pages=None,
        )
    alignment = block_record.get("alignment") or {}
    actual_page_count = alignment.get("page_count")
    if actual_page_count:
        page_count = actual_page_count
        method = "actual"
    else:
        page_count = max(
            1, math.ceil(character_count / configuration.characters_per_estimated_page)
        )
        method = "estimated"
    eligible = page_count <= configuration.max_comment_pages
    return DocumentEligibility(
        eligible=eligible, page_count=page_count, page_count_method=method,
        character_count=character_count,
        maximum_comment_pages=configuration.max_comment_pages,
        exclusion_reason=None if eligible else "excluded-length",
    )


def _task_hash(*, source_hash, block, configuration_hash, task_type):
    identity = (
        f"{source_hash}|{block['block_id']}|{block['plain_text']}|"
        f"{configuration_hash}|{task_type}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _call_and_build_annotation(
    *, caller, configuration, asset, block, index, has_heading,
    target_registry, allowed_targets_by_key, reference_check_requested,
    summary_requested, task_hash
):
    result = asyncio.run(caller(
        model_spec=configuration.summary_model,
        document_type=asset.get("selection_reason", "document"),
        heading_context=" / ".join(block.get("heading_context", [])),
        passage_id=block["block_id"], source_text=block["plain_text"],
        allowed_targets=target_registry,
    ))
    structured_references = []
    if reference_check_requested:
        for reference in result.backward_references:
            if reference.target_key not in allowed_targets_by_key:
                raise ValueError(
                    "structure_pipeline.py Error: model returned unknown target key "
                    f"{reference.target_key!r}"
                )
            structured_references.append({
                "source_block_id": block["block_id"],
                "target_key": reference.target_key,
                "target": allowed_targets_by_key[reference.target_key],
                "search_description": reference.search_description,
            })
    return {
        "block_id": block["block_id"], "task_hash": task_hash,
        "summary_task_hash": _task_hash(
            source_hash=asset["source_sha256"], block=block,
            configuration_hash=f"summary-prompt-{configuration.summary_prompt_version}",
            task_type="summary",
        ),
        "reference_task_hash": _task_hash(
            source_hash=asset["source_sha256"], block=block,
            configuration_hash=(
                f"reference-prompt-{configuration.reference_prompt_version}|"
                + json.dumps(target_registry, sort_keys=True)
            ), task_type="targeted-reference",
        ),
        "task_status": "complete", "summary": result.summary,
        "backward_references": structured_references,
        "reference_check_requested": reference_check_requested,
        "render_summary": summary_requested,
        "placement": (
            "before-block"
            if configuration.summary_mode == "sections" and not has_heading and index == 0
            else "after-block"
        ),
    }


def _render_stage_3(*, stage_2_text, annotations, eligibility, configuration):
    status = "complete" if eligibility.eligible else eligibility.exclusion_reason
    status_block = (
        f"> **Processing status:** {status}\n>\n"
        f"> **Annotation schema:** 1\n>\n"
        f"> **Summary mode:** {configuration.summary_mode}\n>\n"
        f"> **Summary model:** {configuration.summary_model.model_key}\n>\n"
        f"> **Reference model:** {configuration.reference_model.model_key}\n>\n"
        f"> **Comment page count:** {eligibility.page_count if eligibility.page_count is not None else 'not-applicable'}\n>\n"
        f"> **Page count method:** {eligibility.page_count_method}\n"
    )
    front_matter_end = stage_2_text.find("---\n", 4)
    insertion_offset = front_matter_end + 4 if front_matter_end >= 0 else 0
    rendered = stage_2_text[:insertion_offset] + status_block + "\n" + stage_2_text[insertion_offset:]
    if not eligibility.eligible:
        return rendered
    annotation_by_block = {item["block_id"]: item for item in annotations}
    anchor_pattern = re.compile(
        r'<a id="(?P<block_id>(?:section|paragraph|list|quotation|label|table)-\d{4})"></a>'
    )
    matches = list(anchor_pattern.finditer(rendered))
    for match in reversed(matches):
        block_id = match.group("block_id")
        annotation = annotation_by_block.get(block_id)
        if not annotation:
            continue
        next_match = next(
            (candidate for candidate in matches if candidate.start() > match.start()), None
        )
        block_end = next_match.start() if next_match else len(rendered)
        visible_parts = []
        if annotation["render_summary"]:
            visible_parts.append(f"> **In brief:** {annotation['summary']}")
        for reference in annotation["backward_references"]:
            visible_parts.extend([
                f"> **Reference target:** {reference['target']['scope_label']}",
                (
                    f"> **Reference:** Look in {reference['target']['scope_label']} "
                    f"for {reference['search_description']}."
                ),
            ])
        if visible_parts:
            insertion = "\n" + "\n>\n".join(visible_parts) + "\n\n"
            if annotation.get("placement") == "before-block":
                rendered = rendered[:match.start()] + insertion.lstrip() + rendered[match.start():]
            else:
                rendered = rendered[:block_end].rstrip() + insertion + rendered[block_end:]
    return rendered


class StructureDiscoveryPipeline:
    @staticmethod
    def run(
        *, markdown_db_path, configuration, passage_caller=None,
        document_limit=None, source_object_key=None, maximum_api_calls=None,
        requests_per_second=1.0, progress_callback=None, sleeper=None,
        clock=None, source_object_prefix=None, maximum_concurrency=1,
    ):
        if requests_per_second <= 0:
            raise ValueError(
                "structure_pipeline.py Error: requests_per_second must be greater than zero"
            )
        if maximum_concurrency < 1:
            raise ValueError(
                "structure_pipeline.py Error: maximum_concurrency must be at least one"
            )
        caller = passage_caller or MagenticPassageCaller.call
        if passage_caller is None:
            BackendFactory.verify_credentials(
                model_specs=[configuration.summary_model, configuration.reference_model]
            )
        metadata_root = markdown_db_path / "metadata"
        blocks_root = metadata_root / "blocks"
        annotation_root = metadata_root / "structure_discovery" / "annotations"
        config_hash = _configuration_hash(configuration=configuration)
        selected_sleeper = sleeper or time.sleep
        selected_clock = clock or time.monotonic
        started_at = selected_clock()
        last_request_at = None
        completed_documents = 0
        excluded_documents = 0
        failed_tasks = []
        api_calls = 0
        reused_tasks = 0
        completed_tasks = 0
        total_blocks = 0
        selected_document_count = 0
        block_records = [
            (block_path, json.loads(block_path.read_text(encoding="utf-8")))
            for block_path in blocks_root.glob("*.json")
        ]
        block_records.sort(key=lambda item: item[1]["asset"]["source_object_key"])
        submission_ids_with_attachments = {
            submission_id
            for _path, record in block_records
            for submission_id in [
                _submission_id(
                    source_object_key=record["asset"]["source_object_key"]
                )
            ]
            if submission_id
            and "_attachment_" in record["asset"]["source_object_key"]
        }
        inventory_path = metadata_root / "manifests" / "source_inventory.json"
        if inventory_path.is_file():
            inventory_assets = json.loads(
                inventory_path.read_text(encoding="utf-8")
            )["assets"]
            submission_ids_with_attachments.update(
                submission_id
                for asset in inventory_assets
                for submission_id in [
                    _submission_id(source_object_key=asset["source_object_key"])
                ]
                if submission_id and "_attachment_" in asset["source_object_key"]
            )
        for block_path, block_record in block_records:
            asset = block_record["asset"]
            if source_object_key and asset["source_object_key"] != source_object_key:
                continue
            if source_object_prefix and not asset["source_object_key"].startswith(
                source_object_prefix
            ):
                continue
            if document_limit is not None and selected_document_count >= document_limit:
                break
            stage_2_path = markdown_db_path / STAGE_2 / asset["markdown_path"]
            if not stage_2_path.is_file():
                continue
            selected_document_count += 1
            total_blocks += len(block_record["blocks"])
            if progress_callback:
                progress_callback({
                    "event": "document_started",
                    "document_number": selected_document_count,
                    "source_object_key": asset["source_object_key"],
                    "block_count": len(block_record["blocks"]),
                })
            eligibility = document_eligibility(
                block_record=block_record,
                configuration=configuration,
                submission_has_attachment=(
                    _submission_id(
                        source_object_key=asset["source_object_key"]
                    ) in submission_ids_with_attachments
                ),
            )
            target_registry = block_record.get("target_registry", [])
            sidecar_path = annotation_root / block_path.name
            existing = (
                json.loads(sidecar_path.read_text(encoding="utf-8"))
                if sidecar_path.is_file() else {"annotations": []}
            )
            existing_by_hash = {
                item["task_hash"]: item for item in existing.get("annotations", [])
                if item.get("task_status") == "complete"
            }
            annotations = []
            if eligibility.eligible:
                has_heading = any(
                    block["block_type"] == "section" for block in block_record["blocks"]
                )
                allowed_targets_by_key = {
                    target["target_key"]: target for target in target_registry
                }
                pending_tasks = []
                block_order = {
                    block["block_id"]: index
                    for index, block in enumerate(block_record["blocks"])
                }
                for index, block in enumerate(block_record["blocks"]):
                    reference_check_requested = reference_detection_eligible(block=block)
                    summary_requested = (
                        configuration.summary_mode == "deep"
                        or block["block_type"] == "section"
                        or not has_heading and index == 0
                    )
                    if not summary_requested and not reference_check_requested:
                        continue
                    task_hash = _task_hash(
                        source_hash=asset["source_sha256"], block=block,
                        configuration_hash=config_hash,
                        task_type="summary-and-targeted-reference-v2",
                    )
                    if task_hash in existing_by_hash:
                        annotations.append(existing_by_hash[task_hash])
                        reused_tasks += 1
                        completed_tasks += 1
                        if progress_callback:
                            progress_callback({
                                "event": "block_reused",
                                "source_object_key": asset["source_object_key"],
                                "block_id": block["block_id"],
                                "completed_tasks": completed_tasks,
                                "api_calls": api_calls,
                            })
                        continue
                    if maximum_api_calls is not None and api_calls >= maximum_api_calls:
                        failed_tasks.append({
                            "source_object_key": asset["source_object_key"],
                            "block_id": block["block_id"],
                            "error": (
                                "structure_pipeline.py Error: API call budget exhausted "
                                f"at {maximum_api_calls} calls"
                            ),
                        })
                        break
                    pending_tasks.append({
                        "index": index, "block": block, "task_hash": task_hash,
                        "reference_check_requested": reference_check_requested,
                        "summary_requested": summary_requested,
                    })
                futures = {}
                with ThreadPoolExecutor(max_workers=maximum_concurrency) as executor:
                    for task in pending_tasks:
                        if maximum_api_calls is not None and api_calls >= maximum_api_calls:
                            failed_tasks.append({
                                "source_object_key": asset["source_object_key"],
                                "block_id": task["block"]["block_id"],
                                "error": (
                                    "structure_pipeline.py Error: API call budget exhausted "
                                    f"at {maximum_api_calls} calls"
                                ),
                            })
                            continue
                        if last_request_at is not None:
                            elapsed_since_request = selected_clock() - last_request_at
                            required_interval = 1.0 / requests_per_second
                            if elapsed_since_request < required_interval:
                                selected_sleeper(required_interval - elapsed_since_request)
                        api_calls += 1
                        last_request_at = selected_clock()
                        if progress_callback:
                            progress_callback({
                                "event": "api_call_started",
                                "source_object_key": asset["source_object_key"],
                                "block_id": task["block"]["block_id"],
                                "api_call_number": api_calls,
                                "requests_per_second": requests_per_second,
                            })
                        future = executor.submit(
                            _call_and_build_annotation,
                            caller=caller, configuration=configuration, asset=asset,
                            block=task["block"], index=task["index"],
                            has_heading=has_heading, target_registry=target_registry,
                            allowed_targets_by_key=allowed_targets_by_key,
                            reference_check_requested=task["reference_check_requested"],
                            summary_requested=task["summary_requested"],
                            task_hash=task["task_hash"],
                        )
                        futures[future] = task["block"]
                    for future in as_completed(futures):
                        block = futures[future]
                        try:
                            annotations.append(future.result())
                            completed_tasks += 1
                            if progress_callback:
                                progress_callback({
                                    "event": "api_call_completed",
                                    "source_object_key": asset["source_object_key"],
                                    "block_id": block["block_id"],
                                    "completed_tasks": completed_tasks,
                                    "api_calls": api_calls,
                                })
                        except Exception as error:
                            failed_tasks.append({
                                "source_object_key": asset["source_object_key"],
                                "block_id": block["block_id"],
                                "error": (
                                    "structure_pipeline.py Error: model call failed "
                                    f"validation with {type(error).__name__}"
                                ),
                            })
                annotations.sort(key=lambda item: block_order[item["block_id"]])
            else:
                excluded_documents += 1
                annotations = []
                if progress_callback:
                    progress_callback({
                        "event": "document_excluded",
                        "document_number": selected_document_count,
                        "source_object_key": asset["source_object_key"],
                        "exclusion_reason": eligibility.exclusion_reason,
                    })
            _write_json(
                output_path=sidecar_path,
                value={
                    "schema_version": 1, "asset": asset,
                    "configuration_hash": config_hash,
                    "eligibility": eligibility.model_dump(mode="json"),
                    "target_registry": target_registry,
                    "annotations": annotations,
                },
            )
            stage_3_text = _render_stage_3(
                stage_2_text=stage_2_path.read_text(encoding="utf-8"),
                annotations=annotations, eligibility=eligibility,
                configuration=configuration,
            )
            _write_text(
                output_path=markdown_db_path / STAGE_3 / asset["markdown_path"],
                text=stage_3_text,
            )
            completed_documents += 1
            if progress_callback:
                progress_callback({
                    "event": "document_completed",
                    "document_number": selected_document_count,
                    "source_object_key": asset["source_object_key"],
                    "completed_documents": completed_documents,
                    "excluded_documents": excluded_documents,
                    "failed_task_count": len(failed_tasks),
                    "api_calls": api_calls,
                    "reused_tasks": reused_tasks,
                })
        return {
            "completed_documents": completed_documents,
            "excluded_documents": excluded_documents,
            "failed_task_count": len(failed_tasks),
            "failed_tasks": failed_tasks,
            "api_calls": api_calls,
            "selected_documents": selected_document_count,
            "maximum_api_calls": maximum_api_calls,
            "requests_per_second": requests_per_second,
            "total_blocks": total_blocks,
            "completed_tasks": completed_tasks,
            "reused_tasks": reused_tasks,
            "elapsed_seconds": round(selected_clock() - started_at, 3),
            "model_key": configuration.summary_model.model_key,
            "token_usage_status": "unavailable-from-current-magentic-typed-call",
        }