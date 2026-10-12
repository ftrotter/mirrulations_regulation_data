#!/usr/bin/env python3
"""Run and validate a deterministic sampled Stage 3 quality review."""

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.stage3_review_runner import Stage3ReviewRunner  # noqa: E402
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-fraction", type=float, required=True)
    arguments = parser.parse_args()
    try:
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

        report = Stage3ReviewRunner.run(
            markdown_db_path=_repository_path(setting_name="markdown_db"),
            source_root=_repository_path(setting_name="source_root"),
            configuration=load_structure_configuration(
                configuration_path=_repository_path(setting_name="configuration")
            ),
            output_directory=_repository_path(setting_name="output_directory"),
            sample_fraction=arguments.sample_fraction,
            maximum_api_calls=_environment_integer(
                setting_name="maximum_api_calls", allow_empty=True
            ),
            requests_per_second=_environment_float(
                setting_name="requests_per_second"
            ),
            maximum_concurrency=_environment_integer(
                setting_name="maximum_concurrency"
            ),
            maximum_owned_blocks=_environment_integer(
                setting_name="maximum_owned_blocks"
            ),
            maximum_segment_characters=_environment_integer(
                setting_name="maximum_segment_characters"
            ),
            unstructured_owned_blocks=_environment_integer(
                setting_name="unstructured_owned_blocks"
            ),
            progress_callback=print_progress,
        )
    except ValueError as error:
        parser.exit(1, f"stage3_review.py Error: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "complete":
        parser.exit(1, "stage3_review.py Error: review run is incomplete\n")


if __name__ == "__main__":
    main()