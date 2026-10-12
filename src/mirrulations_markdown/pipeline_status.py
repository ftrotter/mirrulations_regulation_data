"""Introspect authoritative artifacts across all Markdown pipeline stages."""

from collections import Counter
import json
import os
from pathlib import Path

from .analysis_segments import ANALYZABLE_TYPES, build_analysis_segments
from .pipeline import STAGE_1, STAGE_2
from .reference_linker import STAGE_4
from .structure_pipeline import STAGE_3


KNOWN_PID_FILES = (
    "mirrulations_contextual_full.pid",
    "mirrulations_contextual_retry.pid",
    "mirrulations_stage3_quality.pid",
    "mirrulations_stage3_full.pid",
    "mirrulations_reference_linker.pid",
)


def _json(*, path):
    return json.loads(path.read_text(encoding="utf-8"))


def _file_count(*, root):
    return sum(1 for path in root.rglob("*.md") if path.is_file()) if root.is_dir() else 0


def _completion_status(*, actual, expected, errors=0):
    if actual == 0:
        return "not-started"
    if errors == 0 and actual == expected:
        return "complete"
    return "partial"


def _active_processes(*, runtime_directory):
    processes = []
    for file_name in KNOWN_PID_FILES:
        pid_path = runtime_directory / file_name
        if not pid_path.is_file():
            continue
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            running = True
        except (OSError, ValueError):
            pid = None
            running = False
        processes.append({
            "pid_file": str(pid_path), "pid": pid, "running": running,
        })
    return processes


def _last_nonempty_line(*, path):
    if not path.is_file():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return next((line for line in reversed(lines) if line), None)


def _premium_benchmark_processes(*, metadata_root, runtime_directory):
    """Discover and summarize provider jobs in nested Stage 4 runtime directories."""
    processes = []
    pid_paths = (
        sorted(runtime_directory.glob("mirrulations-stage4-*/*.pid"))
        if runtime_directory.is_dir() else []
    )
    benchmark_root = metadata_root / "reference_link_benchmarks"
    cohort_manifests = sorted(benchmark_root.glob("benchmark-*/manifest.json"))
    cohort = _json(path=cohort_manifests[-1]) if cohort_manifests else {}
    for pid_path in pid_paths:
        provider = pid_path.stem
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            running = True
        except (OSError, ValueError):
            pid = None
            running = False
        provider_root = benchmark_root / provider
        accepted_reference_ids = set()
        accepted_batch_files = 0
        if provider_root.is_dir():
            for batch_path in provider_root.glob("*/*/batches/*.json"):
                accepted_batch_files += 1
                accepted_reference_ids.update(
                    link["reference_id"]
                    for link in _json(path=batch_path).get("links", [])
                )
        rejected_paths = (
            list(provider_root.glob("*/*/rejected_batches/*.json"))
            if provider_root.is_dir() else []
        )
        provider_manifests = (
            sorted(provider_root.glob("*/*/manifest.json"), key=lambda path: path.stat().st_mtime_ns)
            if provider_root.is_dir() else []
        )
        provider_manifest = (
            _json(path=provider_manifests[-1]) if provider_manifests else {}
        )
        processes.append({
            "kind": "premium_stage4_benchmark",
            "provider": provider,
            "runtime_name": pid_path.parent.name,
            "pid_file": str(pid_path),
            "pid": pid,
            "running": running,
            "log_path": str(pid_path.with_suffix(".log")),
            "latest_log_line": _last_nonempty_line(path=pid_path.with_suffix(".log")),
            "cohort_comments": cohort.get("comment_count"),
            "cohort_references": cohort.get("reference_count"),
            "accepted_references": len(accepted_reference_ids),
            "accepted_batch_files": accepted_batch_files,
            "rejected_batch_files": len(rejected_paths),
            "manifest_completed_references": provider_manifest.get("references_completed"),
            "manifest_failed_batches": provider_manifest.get("failed_batch_count"),
            "model": provider_manifest.get("model"),
        })
    return processes


def pipeline_status(*, markdown_db_path, runtime_directory=Path("/tmp")):
    """Return one compact status document derived from pipeline artifacts."""
    metadata_root = markdown_db_path / "metadata"
    block_root = metadata_root / "blocks"
    block_records = {
        path.name: _json(path=path) for path in block_root.glob("*.json")
    } if block_root.is_dir() else {}
    expected_documents = len(block_records)

    inventory_path = metadata_root / "manifests" / "source_inventory.json"
    inventory_assets = (
        _json(path=inventory_path).get("assets", []) if inventory_path.is_file() else []
    )
    latest_path = metadata_root / "runs" / "latest.json"
    latest = _json(path=latest_path) if latest_path.is_file() else {}
    source = {
        "status": "complete" if inventory_assets and not latest.get("failed_asset_count", 0) else (
            "partial" if inventory_assets else "not-started"
        ),
        "inventory_assets": len(inventory_assets),
        "markdown_documents_selected": expected_documents,
        "last_run_failed_assets": latest.get("failed_asset_count"),
    }

    stage_1_files = _file_count(root=markdown_db_path / STAGE_1)
    stage_1 = {
        "status": _completion_status(actual=stage_1_files, expected=expected_documents),
        "files": stage_1_files, "expected_files": expected_documents,
        "semantic_blocks": sum(len(record.get("blocks", [])) for record in block_records.values()),
        "block_types": dict(sorted(Counter(
            block["block_type"]
            for record in block_records.values() for block in record.get("blocks", [])
        ).items())),
    }

    citation_root = metadata_root / "annotations" / "citations"
    citation_documents = 0
    citations = []
    if citation_root.is_dir():
        for path in citation_root.glob("*.json"):
            citation_documents += 1
            citations.extend(_json(path=path).get("citations", []))
    stage_2_files = _file_count(root=markdown_db_path / STAGE_2)
    stage_2 = {
        "status": _completion_status(
            actual=min(stage_2_files, citation_documents), expected=expected_documents
        ),
        "files": stage_2_files, "expected_files": expected_documents,
        "citation_sidecars": citation_documents, "citations": len(citations),
        "citation_resolution": dict(sorted(Counter(
            citation.get("resolution_status", "not-recorded") for citation in citations
        ).items())),
    }

    structure_root = metadata_root / "structure_discovery" / "annotations"
    stage_3_sidecars = {
        path.name: _json(path=path) for path in structure_root.glob("*.json")
    } if structure_root.is_dir() else {}
    eligible_documents = 0
    excluded_documents = 0
    missing_owned_blocks = 0
    extra_owned_blocks = 0
    annotations = []
    completed_segments = 0
    planned_segments = 0
    exclusion_reasons = Counter()
    for name, sidecar in stage_3_sidecars.items():
        eligibility = sidecar.get("eligibility", {})
        is_eligible = eligibility.get("eligible", False)
        if is_eligible:
            eligible_documents += 1
        else:
            excluded_documents += 1
            exclusion_reasons[eligibility.get("exclusion_reason") or "not-recorded"] += 1
        document_annotations = sidecar.get("annotations", [])
        annotations.extend(document_annotations)
        document_segment_hashes = {
            annotation["segment_task_hash"] for annotation in document_annotations
            if annotation.get("segment_task_hash")
        }
        completed_segments += len(document_segment_hashes)
        record = block_records.get(name)
        if not record or not is_eligible:
            continue
        expected_ids = {
            block["block_id"] for block in record.get("blocks", [])
            if block["block_type"] in ANALYZABLE_TYPES
        }
        actual_ids = {
            annotation["block_id"] for annotation in document_annotations
            if annotation["block_id"] in expected_ids
            or not annotation["block_id"].startswith("section-")
        }
        missing_owned_blocks += len(expected_ids - actual_ids)
        extra_owned_blocks += len(actual_ids - expected_ids)
        planned_segments += len(build_analysis_segments(blocks=record.get("blocks", [])))
    references = [
        reference for annotation in annotations
        for reference in annotation.get("backward_references", [])
    ]
    stage_3_files = _file_count(root=markdown_db_path / STAGE_3)
    stage_3_errors = missing_owned_blocks + extra_owned_blocks
    stage_3 = {
        "status": _completion_status(
            actual=len(stage_3_sidecars), expected=expected_documents,
            errors=stage_3_errors,
        ),
        "files": stage_3_files, "sidecars": len(stage_3_sidecars),
        "expected_documents": expected_documents,
        "eligible_documents": eligible_documents,
        "excluded_documents": excluded_documents,
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        "planned_segments_for_eligible_documents": planned_segments,
        "completed_segments": completed_segments,
        "annotations": len(annotations), "references": len(references),
        "missing_owned_blocks": missing_owned_blocks,
        "extra_owned_blocks": extra_owned_blocks,
    }

    link_root = metadata_root / "reference_links"
    link_sidecars = {
        path.name: _json(path=path) for path in link_root.glob("*.json")
    } if link_root.is_dir() else {}
    links = [link for sidecar in link_sidecars.values() for link in sidecar.get("links", [])]
    reference_keys = {
        (
            sidecar["asset"]["source_object_key"], reference["source_block_id"],
            reference["target_key"], reference["search_description"],
        )
        for sidecar in stage_3_sidecars.values()
        for annotation in sidecar.get("annotations", [])
        for reference in annotation.get("backward_references", [])
    }
    linked_keys = {
        (
            sidecar["asset"]["source_object_key"], link["source_block_id"],
            link["target_key"], link["search_description"],
        )
        for sidecar in link_sidecars.values() for link in sidecar.get("links", [])
    }
    link_statuses = Counter(link.get("status", "not-recorded") for link in links)
    unresolved_references = len(reference_keys - linked_keys)
    extra_link_records = len(linked_keys - reference_keys)
    stage_4_files = _file_count(root=markdown_db_path / STAGE_4)
    stage_4 = {
        "status": _completion_status(
            actual=len(linked_keys), expected=len(reference_keys),
            errors=unresolved_references + extra_link_records,
        ),
        "files": stage_4_files, "link_sidecars": len(link_sidecars),
        "references_to_resolve": len(reference_keys),
        "link_records": len(linked_keys),
        "linked": link_statuses.get("linked", 0),
        "no_match": link_statuses.get("no-match", 0),
        "failed_or_other": sum(
            count for status, count in link_statuses.items()
            if status not in {"linked", "no-match"}
        ),
        "unresolved_references": unresolved_references,
        "extra_link_records": extra_link_records,
    }

    return {
        "schema_version": 1,
        "markdown_db_path": str(markdown_db_path),
        "source": source,
        "stage001": stage_1,
        "stage002": stage_2,
        "stage003": stage_3,
        "stage004": stage_4,
        "processes": _active_processes(runtime_directory=runtime_directory),
        "premium_benchmark_processes": _premium_benchmark_processes(
            metadata_root=metadata_root, runtime_directory=runtime_directory,
        ),
    }


def format_pipeline_status(*, status):
    """Render a concise human-readable status report."""
    source = status["source"]
    stage_1 = status["stage001"]
    stage_2 = status["stage002"]
    stage_3 = status["stage003"]
    stage_4 = status["stage004"]
    running = [process for process in status["processes"] if process["running"]]
    benchmark_processes = status.get("premium_benchmark_processes", [])
    lines = [
        "Pipeline status",
        f"Source: {source['status']} — {source['inventory_assets']} assets; "
        f"{source['markdown_documents_selected']} selected documents",
        f"Stage 1: {stage_1['status']} — {stage_1['files']}/{stage_1['expected_files']} "
        f"Markdown files; {stage_1['semantic_blocks']} semantic blocks",
        f"Stage 2: {stage_2['status']} — {stage_2['files']}/{stage_2['expected_files']} "
        f"Markdown files; {stage_2['citations']} citations",
        f"Stage 3: {stage_3['status']} — {stage_3['sidecars']}/"
        f"{stage_3['expected_documents']} documents; {stage_3['eligible_documents']} eligible; "
        f"{stage_3['excluded_documents']} excluded; {stage_3['completed_segments']}/"
        f"{stage_3['planned_segments_for_eligible_documents']} segments; "
        f"{stage_3['references']} references; {stage_3['missing_owned_blocks']} missing blocks",
        f"Stage 4: {stage_4['status']} — {stage_4['link_records']}/"
        f"{stage_4['references_to_resolve']} references assessed; "
        f"{stage_4['linked']} linked; {stage_4['no_match']} no-match; "
        f"{stage_4['unresolved_references']} unresolved",
        "Active processes: " + (
            ", ".join(str(process["pid"]) for process in running) if running else "none"
        ),
    ]
    if benchmark_processes:
        lines.append("Premium Stage 4 benchmark processes:")
        for process in benchmark_processes:
            expected = process["cohort_references"]
            expected_text = str(expected) if expected is not None else "not-recorded"
            state = "running" if process["running"] else "stopped"
            lines.append(
                f"- {process['provider']}: {state} pid={process['pid']}; "
                f"{process['accepted_references']}/{expected_text} accepted references; "
                f"{process['accepted_batch_files']} accepted batches; "
                f"{process['rejected_batch_files']} rejected batches"
            )
            if process["latest_log_line"]:
                lines.append(f"  Latest: {process['latest_log_line']}")
    return "\n".join(lines)