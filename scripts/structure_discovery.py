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
from mirrulations_markdown.structure_pipeline import StructureDiscoveryPipeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--document-limit", type=int)
    parser.add_argument("--source-object-key")
    parser.add_argument("--maximum-api-calls", type=int, default=1)
    parser.add_argument("--dotenv", help="Ignored local credential file to load.")
    arguments = parser.parse_args()
    try:
        if arguments.maximum_api_calls < 1:
            raise ValueError("--maximum-api-calls must be at least 1")
        if arguments.dotenv:
            dotenv_path = Path(arguments.dotenv).expanduser().resolve()
            if not dotenv_path.is_file():
                raise ValueError(f"credential file does not exist: {dotenv_path}")
            load_dotenv(dotenv_path=dotenv_path, override=False)
        configuration = load_structure_configuration(
            configuration_path=Path(arguments.configuration).expanduser().resolve()
        )
        result = StructureDiscoveryPipeline.run(
            markdown_db_path=Path(arguments.markdown_db).expanduser().resolve(),
            configuration=configuration,
            document_limit=arguments.document_limit,
            source_object_key=arguments.source_object_key,
            maximum_api_calls=arguments.maximum_api_calls,
        )
    except ValueError as error:
        parser.exit(1, f"structure_discovery.py Error: {error}\n")
    print(json.dumps(result, indent=2))
    if result["failed_task_count"]:
        parser.exit(1, "structure_discovery.py Error: requested work is incomplete\n")


if __name__ == "__main__":
    main()