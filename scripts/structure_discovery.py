#!/usr/bin/env python3
"""Generate immutable Stage 3 summaries and backward references."""

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.structure_configuration import (  # noqa: E402
    load_structure_configuration,
)
from mirrulations_markdown.contextual_structure_pipeline import (  # noqa: E402
    ContextualStructureDiscoveryPipeline,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--document-limit", type=int)
    parser.add_argument("--source-object-key")
    parser.add_argument("--source-object-keys-json")
    parser.add_argument("--source-object-prefix")
    parser.add_argument("--maximum-api-calls", type=int, default=1)
    parser.add_argument(
        "--requests-per-second", type=float, default=1.0,
        help="Positive float; 0.5 means one request every two seconds.",
    )
    parser.add_argument(
        "--maximum-concurrency", type=int, default=1,
        help="Maximum number of simultaneous paid LLM requests.",
    )
    parser.add_argument("--maximum-owned-blocks", type=int, default=20)
    parser.add_argument("--maximum-segment-characters", type=int, default=20000)
    parser.add_argument("--unstructured-owned-blocks", type=int, default=10)
    parser.add_argument("--dotenv", help="Ignored local credential file to load.")
    arguments = parser.parse_args()
    try:
        if arguments.maximum_api_calls < 1:
            raise ValueError("--maximum-api-calls must be at least 1")
        if arguments.requests_per_second <= 0:
            raise ValueError("--requests-per-second must be greater than zero")
        if arguments.maximum_concurrency < 1:
            raise ValueError("--maximum-concurrency must be at least 1")
        if arguments.dotenv:
            dotenv_path = Path(arguments.dotenv).expanduser().resolve()
            if not dotenv_path.is_file():
                raise ValueError(f"credential file does not exist: {dotenv_path}")
            load_dotenv(dotenv_path=dotenv_path, override=False)
        configuration = load_structure_configuration(
            configuration_path=Path(arguments.configuration).expanduser().resolve()
        )
        def print_progress(event):
            event_name = event["event"]
            if event_name == "segment_started":
                print(
                    f"Segment call {event['api_calls']} started: "
                    f"{event['source_object_key']} / {event['segment_id']} "
                    f"({event['owned_block_count']} owned blocks)",
                    flush=True,
                )
            elif event_name == "document_completed":
                print(
                    f"Document complete: {event['source_object_key']} "
                    f"({event['api_calls']} calls, "
                    f"{event['failed_task_count']} failures)",
                    flush=True,
                )

        selected_source_keys = (
            [arguments.source_object_key] if arguments.source_object_key else []
        )
        if arguments.source_object_keys_json:
            selected_source_keys.extend(json.loads(
                Path(arguments.source_object_keys_json).expanduser().resolve().read_text(
                    encoding="utf-8"
                )
            ))
        if arguments.source_object_prefix:
            blocks_root = (
                Path(arguments.markdown_db).expanduser().resolve()
                / "metadata" / "blocks"
            )
            selected_source_keys.extend(
                __import__("json").loads(path.read_text())["asset"]["source_object_key"]
                for path in blocks_root.glob("*.json")
                if __import__("json").loads(path.read_text())["asset"]["source_object_key"].startswith(
                    arguments.source_object_prefix
                )
            )
        result = ContextualStructureDiscoveryPipeline.run(
            markdown_db_path=Path(arguments.markdown_db).expanduser().resolve(),
            configuration=configuration,
            source_object_keys=selected_source_keys,
            maximum_api_calls=arguments.maximum_api_calls,
            requests_per_second=arguments.requests_per_second,
            maximum_concurrency=arguments.maximum_concurrency,
            maximum_owned_blocks=arguments.maximum_owned_blocks,
            maximum_segment_characters=arguments.maximum_segment_characters,
            unstructured_owned_blocks=arguments.unstructured_owned_blocks,
            progress_callback=print_progress,
        )
    except ValueError as error:
        parser.exit(1, f"structure_discovery.py Error: {error}\n")
    print(json.dumps(result, indent=2))
    if result["failed_task_count"]:
        parser.exit(1, "structure_discovery.py Error: requested work is incomplete\n")


if __name__ == "__main__":
    main()