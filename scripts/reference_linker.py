#!/usr/bin/env python3
"""Link Stage 3 comment references to exact regulatory-action blocks."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.reference_linker import ReferenceLinkerPipeline  # noqa: E402
from mirrulations_markdown.structure_configuration import (  # noqa: E402
    load_structure_configuration,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--source-object-key", action="append", default=[])
    parser.add_argument("--source-object-keys-json")
    parser.add_argument("--maximum-api-calls", type=int)
    parser.add_argument("--candidate-limit", type=int, default=12)
    parser.add_argument("--dotenv")
    parser.add_argument(
        "--modified-after",
        help="Only process Stage 3 sidecars modified after this ISO 8601 timestamp.",
    )
    arguments = parser.parse_args()
    try:
        if arguments.maximum_api_calls is not None and arguments.maximum_api_calls < 1:
            raise ValueError("--maximum-api-calls must be at least 1")
        if arguments.candidate_limit < 1:
            raise ValueError("--candidate-limit must be at least 1")
        modified_after = None
        if arguments.modified_after:
            timestamp = arguments.modified_after.replace("Z", "+00:00")
            try:
                modified_after = datetime.fromisoformat(timestamp)
            except ValueError as error:
                raise ValueError(
                    "--modified-after must be an ISO 8601 timestamp"
                ) from error
            if modified_after.tzinfo is None:
                raise ValueError("--modified-after must include a timezone")
            modified_after = modified_after.astimezone(timezone.utc)
        if arguments.dotenv:
            load_dotenv(
                dotenv_path=Path(arguments.dotenv).expanduser().resolve(),
                override=False,
            )
        source_object_keys = list(arguments.source_object_key)
        if arguments.source_object_keys_json:
            json_path = Path(arguments.source_object_keys_json).expanduser().resolve()
            source_object_keys.extend(json.loads(json_path.read_text(encoding="utf-8")))
        configuration = load_structure_configuration(
            configuration_path=Path(arguments.configuration).expanduser().resolve()
        )
        result = ReferenceLinkerPipeline.run(
            markdown_db_path=Path(arguments.markdown_db).expanduser().resolve(),
            model_spec=configuration.reference_model,
            source_object_keys=source_object_keys,
            maximum_api_calls=arguments.maximum_api_calls,
            candidate_limit=arguments.candidate_limit,
            modified_after=modified_after,
            progress_callback=lambda event: print(
                f"Linked {event['source_object_key']} ({event['api_calls']} calls)",
                flush=True,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"reference_linker.py Error: {error}\n")
    print(json.dumps(result, indent=2))
    if result["failed_reference_count"]:
        parser.exit(1, "reference_linker.py Error: requested work is incomplete\n")


if __name__ == "__main__":
    main()