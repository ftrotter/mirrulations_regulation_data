#!/usr/bin/env python3
"""Report authoritative status across all Mirrulations Markdown stages."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.configuration import DEFAULT_MARKDOWN_DB_PATH  # noqa: E402
from mirrulations_markdown.pipeline_status import (  # noqa: E402
    format_pipeline_status, pipeline_status,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", default=str(DEFAULT_MARKDOWN_DB_PATH))
    parser.add_argument("--runtime-directory", default="/tmp")
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args()
    status = pipeline_status(
        markdown_db_path=Path(arguments.markdown_db).expanduser().resolve(),
        runtime_directory=Path(arguments.runtime_directory).expanduser().resolve(),
    )
    print(
        json.dumps(status, indent=2, sort_keys=True)
        if arguments.as_json else format_pipeline_status(status=status)
    )


if __name__ == "__main__":
    main()