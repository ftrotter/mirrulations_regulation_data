"""Reproducible, failure-aware runner for sampled Stage 3 quality reviews."""

import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from .analysis_segments import ANALYZABLE_TYPES, build_analysis_segments
from .contextual_structure_pipeline import ContextualStructureDiscoveryPipeline
from .llm_backend import BackendFactory, MagenticSegmentCaller
from .structure_pipeline import _submission_id, document_eligibility
from .validation import capture_tree_hashes, compare_tree_hashes


class Stage3ReviewRunner:
    """Select, run, and validate a deterministic Stage 3 review cohort."""

    @staticmethod
    def _write_json(*, output_path, value):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _provider_error_details(*, error):
        """Return actionable allowlisted provider fields without raw request data."""
        status_code = getattr(error, "status_code", None)
        body = getattr(error, "body", None)
        provider_error = None
        if isinstance(body, dict):
            provider_error = body.get("error", body)
        elif isinstance(body, list) and body and isinstance(body[0], dict):
            provider_error = body[0].get("error", body[0])
        if not isinstance(provider_error, dict):
            return None
        details = {
            key: provider_error[key]
            for key in ("code", "status", "message")
            if isinstance(provider_error.get(key), (str, int))
        }
        if status_code is not None:
            details["http_status"] = status_code
        return details or None

    @staticmethod
    def _load_block_records(*, markdown_db_path):
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (markdown_db_path / "metadata" / "blocks").glob("*.json")
        ]
        return sorted(records, key=lambda record: record["asset"]["source_object_key"])

    @staticmethod
    def _eligible_records(*, block_records, configuration):
        attachment_submissions = {
            submission_id
            for record in block_records
            for submission_id in [
                _submission_id(source_object_key=record["asset"]["source_object_key"])
            ]
            if submission_id and "_attachment_" in record["asset"]["source_object_key"]
        }
        return [
            record for record in block_records
            if document_eligibility(
                block_record=record,
                configuration=configuration,
                submission_has_attachment=(
                    _submission_id(
                        source_object_key=record["asset"]["source_object_key"]
                    ) in attachment_submissions
                ),
            ).eligible
        ]

    @staticmethod
    def _allocate_role_counts(*, records_by_role, sample_count):
        populated_roles = sorted(records_by_role)
        if sample_count < len(populated_roles):
            raise ValueError(
                "stage3_review_runner.py Error: sample is too small to include every "
                "logical document role"
            )
        population_count = sum(len(records) for records in records_by_role.values())
        exact_counts = {
            role: len(records_by_role[role]) * sample_count / population_count
            for role in populated_roles
        }
        role_counts = {
            role: min(len(records_by_role[role]), max(1, int(exact_counts[role])))
            for role in populated_roles
        }
        while sum(role_counts.values()) < sample_count:
            candidates = [
                role for role in populated_roles
                if role_counts[role] < len(records_by_role[role])
            ]
            selected_role = max(
                candidates,
                key=lambda role: (exact_counts[role] - role_counts[role], role),
            )
            role_counts[selected_role] += 1
        while sum(role_counts.values()) > sample_count:
            candidates = [role for role in populated_roles if role_counts[role] > 1]
            selected_role = min(
                candidates,
                key=lambda role: (exact_counts[role] - role_counts[role], role),
            )
            role_counts[selected_role] -= 1
        return role_counts

    @staticmethod
    def select_cohort(
        *, block_records, configuration, sample_fraction,
        excluded_nonregulatory_source_keys=None,
    ):
        if not 0 < sample_fraction <= 1:
            raise ValueError(
                "stage3_review_runner.py Error: sample fraction must be greater than "
                "zero and no greater than one"
            )
        eligible_records = Stage3ReviewRunner._eligible_records(
            block_records=block_records, configuration=configuration
        )
        regulatory_records = [
            record for record in eligible_records
            if record.get("document_metadata", {}).get("logical_document_role")
            == "regulatory_document"
        ]
        sample_count = max(1, round(len(eligible_records) * sample_fraction))
        if len(regulatory_records) > sample_count:
            raise ValueError(
                "stage3_review_runner.py Error: sample is too small to include every "
                "eligible regulatory action"
            )
        nonregulatory_records = [
            record for record in eligible_records
            if record not in regulatory_records
            and record["asset"]["source_object_key"]
            not in set(excluded_nonregulatory_source_keys or [])
        ]
        records_by_role = defaultdict(list)
        for record in nonregulatory_records:
            role = record.get("document_metadata", {}).get(
                "logical_document_role", "role-not-recorded"
            )
            records_by_role[role].append(record)
        role_counts = Stage3ReviewRunner._allocate_role_counts(
            records_by_role=records_by_role,
            sample_count=sample_count - len(regulatory_records),
        )
        selected_records = list(regulatory_records)
        for role, records in sorted(records_by_role.items()):
            ordered_records = sorted(
                records,
                key=lambda record: hashlib.sha256(
                    record["asset"]["source_object_key"].encode("utf-8")
                ).hexdigest(),
            )
            selected_records.extend(ordered_records[:role_counts[role]])
        selected_records.sort(key=lambda record: record["asset"]["source_object_key"])
        return eligible_records, selected_records

    @staticmethod
    def _preflight(*, configuration, segment_caller):
        if segment_caller is MagenticSegmentCaller.call:
            BackendFactory.verify_credentials(model_specs=[configuration.summary_model])
        result = asyncio.run(segment_caller(
            model_spec=configuration.summary_model,
            document_type="stage3-review-preflight",
            section_heading=None,
            owned_block_ids=["preflight-0001"],
            allowed_targets=[],
            segment_blocks=[{
                "block_id": "preflight-0001",
                "plain_text": "This is a provider availability check.",
                "analysis_role": "owned",
            }],
        ))
        returned_ids = [item.block_id for item in result.block_results]
        if returned_ids != ["preflight-0001"]:
            raise ValueError(
                "stage3_review_runner.py Error: provider preflight returned an "
                "unexpected block identifier"
            )

    @staticmethod
    def _cohort_validation(*, markdown_db_path, selected_records):
        annotation_root = (
            markdown_db_path / "metadata" / "structure_discovery" / "annotations"
        )
        stale_target_registries = 0
        missing_owned_blocks = 0
        reference_count = 0
        annotation_count = 0
        for record in selected_records:
            metadata_name = hashlib.sha256(
                record["asset"]["source_object_key"].encode("utf-8")
            ).hexdigest()
            sidecar_path = annotation_root / f"{metadata_name}.json"
            if not sidecar_path.is_file():
                missing_owned_blocks += sum(
                    block["block_type"] in ANALYZABLE_TYPES
                    for block in record.get("blocks", [])
                )
                continue
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            stale_target_registries += (
                sidecar.get("target_registry", []) != record.get("target_registry", [])
            )
            annotations = sidecar.get("annotations", [])
            annotation_count += len(annotations)
            actual_ids = {annotation["block_id"] for annotation in annotations}
            expected_ids = {
                block["block_id"] for block in record.get("blocks", [])
                if block["block_type"] in ANALYZABLE_TYPES
            }
            missing_owned_blocks += len(expected_ids - actual_ids)
            reference_count += sum(
                len(annotation.get("backward_references", []))
                for annotation in annotations
            )
        return {
            "annotation_count": annotation_count,
            "reference_count": reference_count,
            "missing_owned_blocks": missing_owned_blocks,
            "stale_target_registries": stale_target_registries,
        }

    @staticmethod
    def _determine_status(
        *, failed_segments, completion_percent, structurally_valid,
        problem_tolerance_percent=95.0,
    ):
        if structurally_valid and failed_segments == 0:
            return "complete"
        if structurally_valid and completion_percent >= problem_tolerance_percent:
            return "complete-with-problems"
        return "partial"

    @staticmethod
    def run(
        *, markdown_db_path, source_root, configuration, output_directory,
        sample_fraction=0.10, maximum_api_calls=None, requests_per_second=1.0,
        maximum_concurrency=1, maximum_owned_blocks=20,
        maximum_segment_characters=20000, unstructured_owned_blocks=10,
        segment_caller=MagenticSegmentCaller.call, progress_callback=None,
        excluded_nonregulatory_source_keys=None,
    ):
        block_records = Stage3ReviewRunner._load_block_records(
            markdown_db_path=markdown_db_path
        )
        eligible_records, selected_records = Stage3ReviewRunner.select_cohort(
            block_records=block_records,
            configuration=configuration,
            sample_fraction=sample_fraction,
            excluded_nonregulatory_source_keys=excluded_nonregulatory_source_keys,
        )
        selected_keys = [
            record["asset"]["source_object_key"] for record in selected_records
        ]
        # A full run also refreshes excluded-document sidecars. These documents
        # require no model calls, but their current eligibility and target
        # registries are necessary for corpus-wide Stage 3 completion.
        pipeline_source_keys = list(selected_keys)
        if sample_fraction == 1 and not excluded_nonregulatory_source_keys:
            pipeline_source_keys = [
                record["asset"]["source_object_key"] for record in block_records
            ]
        expected_segment_calls = sum(
            len(build_analysis_segments(
                blocks=record.get("blocks", []),
                maximum_owned_blocks=maximum_owned_blocks,
                maximum_characters=maximum_segment_characters,
                unstructured_owned_blocks=unstructured_owned_blocks,
            ))
            for record in selected_records
        )
        effective_api_budget = maximum_api_calls or expected_segment_calls
        manifest = {
            "schema_version": 1,
            "selection_method": "sha256-order-stratified-by-logical-document-role",
            "eligible_document_count": len(eligible_records),
            "sample_document_count": len(selected_records),
            "sample_fraction_requested": sample_fraction,
            "sample_fraction_actual": len(selected_records) / len(eligible_records),
            "role_population": dict(sorted(Counter(
                record.get("document_metadata", {}).get(
                    "logical_document_role", "role-not-recorded"
                ) for record in eligible_records
            ).items())),
            "role_sample": dict(sorted(Counter(
                record.get("document_metadata", {}).get(
                    "logical_document_role", "role-not-recorded"
                ) for record in selected_records
            ).items())),
            "expected_segment_calls": expected_segment_calls,
            "maximum_api_calls": effective_api_budget,
            "source_object_keys_file": "source_object_keys.json",
        }
        Stage3ReviewRunner._write_json(
            output_path=output_directory / "manifest.json", value=manifest
        )
        Stage3ReviewRunner._write_json(
            output_path=output_directory / "source_object_keys.json",
            value=selected_keys,
        )
        before_hashes = capture_tree_hashes(
            source_root=source_root, markdown_db_path=markdown_db_path
        )
        report = {"schema_version": 1, "manifest": manifest, "status": "preflight"}
        try:
            Stage3ReviewRunner._preflight(
                configuration=configuration, segment_caller=segment_caller
            )
            report["status"] = "running"
            pipeline_result = ContextualStructureDiscoveryPipeline.run(
                markdown_db_path=markdown_db_path,
                configuration=configuration,
                source_object_keys=pipeline_source_keys,
                maximum_api_calls=effective_api_budget,
                requests_per_second=requests_per_second,
                maximum_concurrency=maximum_concurrency,
                maximum_owned_blocks=maximum_owned_blocks,
                maximum_segment_characters=maximum_segment_characters,
                unstructured_owned_blocks=unstructured_owned_blocks,
                segment_caller=segment_caller,
                progress_callback=progress_callback,
            )
            report["pipeline_result"] = pipeline_result
        except Exception as error:
            report["status"] = "failed"
            provider_error = Stage3ReviewRunner._provider_error_details(error=error)
            report["error"] = (
                "stage3_review_runner.py Error: review run failed with "
                f"{type(error).__name__}"
            )
            if provider_error:
                report["provider_error"] = provider_error
                report["error"] += ": " + str(provider_error.get(
                    "message", "provider request failed"
                ))
            Stage3ReviewRunner._write_json(
                output_path=output_directory / "report.json", value=report
            )
            raise ValueError(report["error"]) from error
        after_hashes = capture_tree_hashes(
            source_root=source_root, markdown_db_path=markdown_db_path
        )
        changed_trees = compare_tree_hashes(
            before_hashes=before_hashes, after_hashes=after_hashes
        )
        cohort_validation = Stage3ReviewRunner._cohort_validation(
            markdown_db_path=markdown_db_path, selected_records=selected_records
        )
        total_segments = expected_segment_calls
        failed_segments = pipeline_result["failed_task_count"]
        successful_segments = max(0, total_segments - failed_segments)
        completion_percent = (
            round(successful_segments / total_segments * 100, 2)
            if total_segments else 100.0
        )
        problem_tolerance_percent = 95.0
        structurally_valid = (
            not changed_trees
            and not cohort_validation["missing_owned_blocks"]
            and not cohort_validation["stale_target_registries"]
        )
        status = Stage3ReviewRunner._determine_status(
            failed_segments=failed_segments,
            completion_percent=completion_percent,
            structurally_valid=structurally_valid,
            problem_tolerance_percent=problem_tolerance_percent,
        )
        report.update({
            "status": status,
            "completion_percent": completion_percent,
            "successful_segments": successful_segments,
            "total_segments": total_segments,
            "problematic_segment_count": failed_segments,
            "problem_tolerance_percent": problem_tolerance_percent,
            "immutable_tree_hashes_before": before_hashes,
            "immutable_tree_hashes_after": after_hashes,
            "changed_immutable_trees": changed_trees,
            "cohort_validation": cohort_validation,
        })
        Stage3ReviewRunner._write_json(
            output_path=output_directory / "report.json", value=report
        )
        return report