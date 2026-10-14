#!/usr/bin/env python3
"""Run a reproducible OpenAI review of production Stage 4 outcomes."""

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.stage4_quality_review import (  # noqa: E402
    DEFAULT_OPENAI_MODEL, Stage4QualityReviewRunner,
)
from mirrulations_markdown.local_run_manager import LocalRunManager  # noqa: E402


def _path_from_environment(*, name, default):
    value = os.getenv(name, default)
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (REPOSITORY_ROOT / path).resolve()


def _run_root():
    return REPOSITORY_ROOT / ".local" / "pipeline_runs" / "stage4_quality_review"


def _load_environment():
    environment_path = REPOSITORY_ROOT / ".env"
    if environment_path.is_file():
        load_dotenv(dotenv_path=environment_path, override=False)


def _review_output_directory():
    return _path_from_environment(
        name="STAGE4_QUALITY_REVIEW_OUTPUT_DIRECTORY",
        default="data/markdown_db/metadata/stage4_quality_review_openai_50",
    )


def _review_progress(*, status):
    output_directory = _review_output_directory()
    manifest_path = output_directory / "manifest.json"
    report_path = output_directory / "report.json"
    expected = 0
    if manifest_path.is_file():
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))["sample_count"]
    judgments_directory = output_directory / "judgments"
    completed = len(list(judgments_directory.glob("*.json"))) if judgments_directory.is_dir() else 0
    progress = {
        "reviews_completed": completed,
        "reviews_expected": expected,
        "percent_complete": round(100 * completed / expected, 1) if expected else 0.0,
        "report_path": str(report_path),
    }
    if report_path.is_file():
        progress["review_report"] = json.loads(report_path.read_text(encoding="utf-8"))
    combined = {**status, **progress}
    if (
        combined["status"] == "finished"
        and combined.get("review_report", {}).get("status") != "complete"
        and "Error:" in (combined.get("last_log_line") or "")
    ):
        combined["status"] = "failed"
    return combined


def _print_review_status(*, status):
    attention = status.get("attention_required")
    if attention:
        print("\aATTENTION REQUIRED")
        print(f"Reason: {attention['message']}")
        if attention.get("action_url"):
            print(f"Action: {attention['action_url']}")
    print(f"Status: {status['status']}")
    if status.get("reviews_expected"):
        print(
            f"Progress: {status['percent_complete']}% "
            f"({status['reviews_completed']}/{status['reviews_expected']} reviews)"
        )
    if status.get("pid"):
        print(f"PID: {status['pid']}")
    if status.get("log_path"):
        print(f"Log: {status['log_path']}")
    if status.get("last_log_line"):
        print(f"Latest: {status['last_log_line']}")
    report = status.get("review_report")
    if report:
        print(f"Review report status: {report['status']}")
        print(
            "Production decisions judged correct: "
            f"{report['production_decision_correct_count']}/{report['completed_count']} "
            f"({report['production_decision_correct_percent']}%)"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    for command, help_text in (
        ("start", "Start the review in the background."),
        ("run", "Run the review in the foreground."),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--linked-count", type=int, default=40)
        command_parser.add_argument("--no-match-count", type=int, default=10)
    subparsers.add_parser("status", help="Show review progress and the latest log message.")
    subparsers.add_parser("wait", help="Wait for the current review to finish.")
    arguments = parser.parse_args()
    try:
        _load_environment()
        if arguments.command == "status":
            _print_review_status(status=_review_progress(
                status=LocalRunManager.status(run_root=_run_root()),
            ))
            return
        if arguments.command == "wait":
            _print_review_status(status=_review_progress(
                status=LocalRunManager.wait(run_root=_run_root()),
            ))
            return
        if arguments.command == "start":
            status = LocalRunManager.start(
                run_root=_run_root(),
                command=[
                    sys.executable, str(Path(__file__).resolve()), "run",
                    "--linked-count", str(arguments.linked_count),
                    "--no-match-count", str(arguments.no_match_count),
                ],
                description="OpenAI Stage 4 quality review",
            )
            _print_review_status(status=_review_progress(status=status))
            return
        if arguments.command != "run":
            parser.error("choose start, run, status, or wait")
        if arguments.linked_count < 0 or arguments.no_match_count < 0:
            raise ValueError("sample counts cannot be negative")
        if arguments.linked_count + arguments.no_match_count < 1:
            raise ValueError("at least one review must be requested")
        result = Stage4QualityReviewRunner.run(
            markdown_db_path=_path_from_environment(
                name="STAGE4_QUALITY_REVIEW_MARKDOWN_DB", default="data/markdown_db",
            ),
            output_directory=_review_output_directory(),
            model=os.getenv("STAGE4_QUALITY_REVIEW_OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            linked_count=arguments.linked_count,
            no_match_count=arguments.no_match_count,
            progress_callback=lambda event: print(
                f"Reviewed {event['completed']}/{event['total']}", flush=True
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"stage4_quality_review.py Error: {error}\n")
    except Exception as error:
        if error.__class__.__module__.startswith("openai"):
            error_text = str(error)
            if any(marker in error_text for marker in (
                "credit_balance_exhausted", "insufficient_quota", "no credits remaining",
            )):
                LocalRunManager.signal_attention(
                    category="provider_budget_exhausted",
                    message="OpenAI prepaid credits are exhausted; this run is paused.",
                    action_url="https://platform.openai.com/settings/organization/billing/",
                )
            parser.exit(1, f"stage4_quality_review.py OpenAI Error: {error}\n")
        raise
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()