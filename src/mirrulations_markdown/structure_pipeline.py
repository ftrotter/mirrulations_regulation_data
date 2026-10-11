"""Stage 3 summaries and backward-reference descriptions."""

import asyncio
import hashlib
import json
import math
from pathlib import Path
import re

from .llm_backend import BackendFactory, MagenticPassageCaller
from .pipeline import STAGE_2, _write_json, _write_text
from .structure_models import DocumentEligibility


STAGE_3 = "stage003_structure_discovery"


def _configuration_hash(*, configuration):
    serialized = json.dumps(
        configuration.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def document_eligibility(*, block_record, configuration):
    source_key = block_record["asset"]["source_object_key"]
    is_comment = "/comments/" in source_key or "comments_extracted_text" in source_key
    character_count = sum(len(block["plain_text"]) for block in block_record["blocks"])
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


def _task_hash(*, source_hash, block, configuration_hash):
    identity = (
        f"{source_hash}|{block['block_id']}|{block['plain_text']}|"
        f"{configuration_hash}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _render_stage_3(*, stage_2_text, annotations, eligibility, configuration):
    status = "complete" if eligibility.eligible else "excluded-length"
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
    anchor_pattern = re.compile(r'<a id="(?P<block_id>p-\d{4})"></a>')
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
        visible_parts.extend(
            f"> **Reference:** {reference}"
            for reference in annotation["backward_references"]
        )
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
        document_limit=None, source_object_key=None, maximum_api_calls=None
    ):
        caller = passage_caller or MagenticPassageCaller.call
        if passage_caller is None:
            BackendFactory.verify_credentials(
                model_specs=[configuration.summary_model, configuration.reference_model]
            )
        metadata_root = markdown_db_path / "metadata"
        blocks_root = metadata_root / "blocks"
        annotation_root = metadata_root / "structure_discovery" / "annotations"
        config_hash = _configuration_hash(configuration=configuration)
        completed_documents = 0
        excluded_documents = 0
        failed_tasks = []
        api_calls = 0
        selected_document_count = 0
        for block_path in sorted(blocks_root.glob("*.json")):
            block_record = json.loads(block_path.read_text(encoding="utf-8"))
            asset = block_record["asset"]
            if source_object_key and asset["source_object_key"] != source_object_key:
                continue
            if document_limit is not None and selected_document_count >= document_limit:
                break
            stage_2_path = markdown_db_path / STAGE_2 / asset["markdown_path"]
            if not stage_2_path.is_file():
                continue
            selected_document_count += 1
            eligibility = document_eligibility(
                block_record=block_record, configuration=configuration
            )
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
                    block["block_type"] == "heading" for block in block_record["blocks"]
                )
                for index, block in enumerate(block_record["blocks"]):
                    task_hash = _task_hash(
                        source_hash=asset["source_sha256"], block=block,
                        configuration_hash=config_hash,
                    )
                    if task_hash in existing_by_hash:
                        annotations.append(existing_by_hash[task_hash])
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
                    try:
                        api_calls += 1
                        result = asyncio.run(caller(
                            model_spec=configuration.summary_model,
                            document_type=asset.get("selection_reason", "document"),
                            heading_context=" / ".join(block.get("heading_context", [])),
                            passage_id=block["block_id"], source_text=block["plain_text"],
                        ))
                        annotation = {
                            "block_id": block["block_id"], "task_hash": task_hash,
                            "task_status": "complete", "summary": result.summary,
                            "backward_references": result.backward_references,
                            "render_summary": (
                                configuration.summary_mode == "deep"
                                or block["block_type"] == "heading"
                                or not has_heading and index == 0
                            ),
                            "placement": (
                                "before-block"
                                if configuration.summary_mode == "sections"
                                and not has_heading and index == 0
                                else "after-block"
                            ),
                        }
                        annotations.append(annotation)
                    except Exception as error:
                        failed_tasks.append({
                            "source_object_key": asset["source_object_key"],
                            "block_id": block["block_id"],
                            "error": (
                                "structure_pipeline.py Error: model call failed "
                                f"validation with {type(error).__name__}"
                            ),
                        })
            else:
                excluded_documents += 1
            _write_json(
                output_path=sidecar_path,
                value={
                    "schema_version": 1, "asset": asset,
                    "configuration_hash": config_hash,
                    "eligibility": eligibility.model_dump(mode="json"),
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
        return {
            "completed_documents": completed_documents,
            "excluded_documents": excluded_documents,
            "failed_task_count": len(failed_tasks),
            "failed_tasks": failed_tasks,
            "api_calls": api_calls,
            "selected_documents": selected_document_count,
            "maximum_api_calls": maximum_api_calls,
        }