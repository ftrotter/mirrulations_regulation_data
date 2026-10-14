#!/usr/bin/env python3
"""Run and validate a deterministic sampled Stage 3 quality review."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.stage3_review_runner import Stage3ReviewRunner  # noqa: E402
from mirrulations_markdown.local_run_manager import LocalRunManager  # noqa: E402
from mirrulations_markdown.reference_linker import ReferenceLinkerPipeline  # noqa: E402
from mirrulations_markdown.structure_configuration import (  # noqa: E402
    load_structure_configuration,
)


ENVIRONMENT_SETTINGS = {
    "markdown_db": "STAGE3_REVIEW_MARKDOWN_DB",
    "source_root": "STAGE3_REVIEW_SOURCE_ROOT",
    "configuration": "STAGE3_REVIEW_CONFIGURATION",
    "output_directory": "STAGE3_REVIEW_OUTPUT_DIRECTORY",
    "maximum_api_calls": "STAGE3_REVIEW_MAXIMUM_API_CALLS",
    "requests_per_second": "STAGE3_REVIEW_REQUESTS_PER_SECOND",
    "maximum_concurrency": "STAGE3_REVIEW_MAXIMUM_CONCURRENCY",
    "maximum_owned_blocks": "STAGE3_REVIEW_MAXIMUM_OWNED_BLOCKS",
    "maximum_segment_characters": "STAGE3_REVIEW_MAXIMUM_SEGMENT_CHARACTERS",
    "unstructured_owned_blocks": "STAGE3_REVIEW_UNSTRUCTURED_OWNED_BLOCKS",
    "stage4_maximum_concurrency": "STAGE4_REVIEW_MAXIMUM_CONCURRENCY",
    "stage4_requests_per_second": "STAGE4_REVIEW_REQUESTS_PER_SECOND",
}


def _environment_value(*, setting_name, allow_empty=False):
    variable_name = ENVIRONMENT_SETTINGS[setting_name]
    value = os.getenv(variable_name, "").strip()
    if not value and not allow_empty:
        raise ValueError(f"environment variable {variable_name} is required")
    return value


def _environment_integer(*, setting_name, allow_empty=False):
    raw_value = _environment_value(
        setting_name=setting_name, allow_empty=allow_empty
    )
    if not raw_value and allow_empty:
        return None
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(
            f"environment variable {ENVIRONMENT_SETTINGS[setting_name]} must be an integer"
        ) from error
    if value < 1:
        raise ValueError(
            f"environment variable {ENVIRONMENT_SETTINGS[setting_name]} must be at least 1"
        )
    return value


def _environment_float(*, setting_name):
    raw_value = _environment_value(setting_name=setting_name)
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(
            f"environment variable {ENVIRONMENT_SETTINGS[setting_name]} must be numeric"
        ) from error
    if value <= 0:
        raise ValueError(
            f"environment variable {ENVIRONMENT_SETTINGS[setting_name]} must be positive"
        )
    return value


def _repository_path(*, setting_name):
    configured_path = Path(_environment_value(setting_name=setting_name)).expanduser()
    return (
        configured_path if configured_path.is_absolute()
        else REPOSITORY_ROOT / configured_path
    ).resolve()


def _run_root():
    return REPOSITORY_ROOT / ".local" / "pipeline_runs" / "stage3_review"


def _resolve_output_directory(
    *, sample_fraction, continue_after_current_cohort, configured_output_directory,
):
    if sample_fraction == 1 and not continue_after_current_cohort:
        return configured_output_directory.parent / "stage3_full"
    if continue_after_current_cohort:
        percentage_label = str(sample_fraction * 100).rstrip("0").rstrip(".")
        return configured_output_directory.parent / (
            f"stage3_quality_review_{percentage_label}pct_continuation"
        )
    return configured_output_directory


def _parse_command_flags(*, command):
    sample_fraction = 1.0
    continue_after_current_cohort = False
    if "--sample-fraction" in command:
        sample_fraction = float(command[command.index("--sample-fraction") + 1])
    continue_after_current_cohort = "--continue-after-current-cohort" in command
    return sample_fraction, continue_after_current_cohort


def _compute_progress(*, status):
    """Approximate percent complete from the run log and its manifest."""
    log_path = Path(status.get("log_path", ""))
    lines = (
        log_path.read_text(encoding="utf-8").splitlines()
        if log_path.is_file() else []
    )
    segments_started = 0
    for line in lines:
        match = re.match(r"^Segment (\d+):", line)
        if match:
            segments_started = int(match.group(1))
    stage4_documents = sum(
        1 for line in lines if line.startswith("Stage 4 document:")
    )
    in_stage4 = any(
        "Stage 3 complete; starting Stage 4" in line for line in lines
    )
    sample_fraction, continue_after_current_cohort = _parse_command_flags(
        command=status.get("command", []),
    )
    expected_segments = 0
    try:
        environment_path = REPOSITORY_ROOT / ".env"
        if environment_path.is_file():
            load_dotenv(dotenv_path=environment_path, override=False)
        configured_output_directory = _repository_path(setting_name="output_directory")
        output_directory = _resolve_output_directory(
            sample_fraction=sample_fraction,
            continue_after_current_cohort=continue_after_current_cohort,
            configured_output_directory=configured_output_directory,
        )
        manifest_path = output_directory / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_segments = manifest.get("expected_segment_calls", 0)
    except (OSError, ValueError, KeyError):
        expected_segments = 0
    percent_complete = (
        round(min(100.0, segments_started / expected_segments * 100), 1)
        if expected_segments else 0.0
    )
    return {
        "stage": "4" if in_stage4 else "3",
        "segments_started": segments_started,
        "expected_segments": expected_segments,
        "percent_complete": percent_complete,
        "stage4_documents": stage4_documents,
    }


def _run_review(
    *, sample_fraction, continue_after_current_cohort=False,
    continue_with_stage4=False,
):
    environment_path = REPOSITORY_ROOT / ".env"
    if not environment_path.is_file():
        raise ValueError(
            f"repository environment file does not exist: {environment_path}"
        )
    load_dotenv(dotenv_path=environment_path, override=False)

    def print_progress(event):
        if event["event"] == "segment_started":
            print(
                f"Segment {event['api_calls']}: {event['source_object_key']} / "
                f"{event['segment_id']}", flush=True,
            )

    configured_output_directory = _repository_path(setting_name="output_directory")
    excluded_keys = []
    output_directory = configured_output_directory
    if sample_fraction == 1 and not continue_after_current_cohort:
        output_directory = configured_output_directory.parent / "stage3_full"
    elif continue_after_current_cohort:
        source_keys_path = configured_output_directory / "source_object_keys.json"
        if not source_keys_path.is_file():
            raise ValueError(
                "cannot continue because the current cohort source keys do not exist: "
                f"{source_keys_path}"
            )
        excluded_keys = json.loads(source_keys_path.read_text(encoding="utf-8"))
        percentage_label = str(sample_fraction * 100).rstrip("0").rstrip(".")
        output_directory = configured_output_directory.parent / (
            f"stage3_quality_review_{percentage_label}pct_continuation"
        )
    stage3_started_at = datetime.now(timezone.utc)
    report = Stage3ReviewRunner.run(
        markdown_db_path=_repository_path(setting_name="markdown_db"),
        source_root=_repository_path(setting_name="source_root"),
        configuration=load_structure_configuration(
            configuration_path=_repository_path(setting_name="configuration")
        ),
        output_directory=output_directory,
        sample_fraction=sample_fraction,
        maximum_api_calls=_environment_integer(
            setting_name="maximum_api_calls", allow_empty=True
        ),
        requests_per_second=_environment_float(setting_name="requests_per_second"),
        maximum_concurrency=_environment_integer(setting_name="maximum_concurrency"),
        maximum_owned_blocks=_environment_integer(setting_name="maximum_owned_blocks"),
        maximum_segment_characters=_environment_integer(
            setting_name="maximum_segment_characters"
        ),
        unstructured_owned_blocks=_environment_integer(
            setting_name="unstructured_owned_blocks"
        ),
        progress_callback=print_progress,
        excluded_nonregulatory_source_keys=excluded_keys,
    )
    if continue_with_stage4:
        if report["status"] not in {"complete", "complete-with-problems"}:
            raise ValueError(
                "Stage 4 was not started because Stage 3 did not complete"
            )
        if report["status"] == "complete-with-problems":
            print(
                f"Stage 3 complete with "
                f"{report.get('problematic_segment_count', 0)} problematic segments; "
                "proceeding to Stage 4",
                flush=True,
            )
        print(
            "Stage 3 complete; starting Stage 4 for sidecars modified after "
            f"{stage3_started_at.isoformat()}",
            flush=True,
        )
        configuration = load_structure_configuration(
            configuration_path=_repository_path(setting_name="configuration")
        )
        stage4_result = ReferenceLinkerPipeline.run(
            markdown_db_path=_repository_path(setting_name="markdown_db"),
            model_spec=configuration.reference_model,
            modified_after=stage3_started_at,
            maximum_concurrency=_environment_integer(
                setting_name="stage4_maximum_concurrency"
            ),
            requests_per_second=_environment_float(
                setting_name="stage4_requests_per_second"
            ),
            progress_callback=lambda event: print(
                f"Stage 4 document: {event['source_object_key']} "
                f"({event['api_calls']} calls)",
                flush=True,
            ),
        )
        report["stage4_result"] = stage4_result
        if stage4_result["failed_reference_count"]:
            print(
                f"Stage 4 completed with "
                f"{stage4_result['failed_reference_count']} problematic references",
                flush=True,
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser("start", help="Start a background review run.")
    start_parser.add_argument("--sample-fraction", type=float, required=True)
    start_parser.add_argument("--continue-after-current-cohort", action="store_true")
    start_parser.add_argument("--continue-with-stage4", action="store_true")
    run_parser = subparsers.add_parser("run", help="Run in the foreground.")
    run_parser.add_argument("--sample-fraction", type=float, required=True)
    run_parser.add_argument("--continue-after-current-cohort", action="store_true")
    run_parser.add_argument("--continue-with-stage4", action="store_true")
    subparsers.add_parser("status", help="Show the latest local run status.")
    subparsers.add_parser("wait", help="Wait for the latest local run to finish.")
    parser.add_argument("--sample-fraction", type=float, dest="legacy_sample_fraction")
    arguments = parser.parse_args()
    try:
        if arguments.command == "status":
            status = LocalRunManager.status(run_root=_run_root())
            status.update(_compute_progress(status=status))
            LocalRunManager.print_status(status=status)
            return
        if arguments.command == "wait":
            status = LocalRunManager.wait(run_root=_run_root())
            status.update(_compute_progress(status=status))
            LocalRunManager.print_status(status=status)
            return
        if arguments.command == "start":
            status = LocalRunManager.start(
                run_root=_run_root(),
                command=[
                    sys.executable, str(Path(__file__).resolve()), "run",
                    "--sample-fraction", str(arguments.sample_fraction),
                    *(["--continue-after-current-cohort"]
                      if arguments.continue_after_current_cohort else []),
                    *(["--continue-with-stage4"]
                      if arguments.continue_with_stage4 else []),
                ],
                description="Stage 3 sampled quality review",
            )
            LocalRunManager.print_status(status=status)
            return
        sample_fraction = (
            arguments.sample_fraction
            if arguments.command == "run" else arguments.legacy_sample_fraction
        )
        if sample_fraction is None:
            parser.error("choose start, run, status, or wait")
        report = _run_review(
            sample_fraction=sample_fraction,
            continue_after_current_cohort=getattr(
                arguments, "continue_after_current_cohort", False
            ),
            continue_with_stage4=getattr(arguments, "continue_with_stage4", False),
        )
    except ValueError as error:
        parser.exit(1, f"stage3_review.py Error: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] not in {"complete", "complete-with-problems"}:
        parser.exit(1, "stage3_review.py Error: review run is incomplete\n")


if __name__ == "__main__":
    main()