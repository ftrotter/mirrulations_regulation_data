#!/usr/bin/env python3
"""Run regulatory extraction, CorEx topic modeling, and graph generation."""

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.topic_pipeline import run_topic_pipeline  # noqa: E402


def _resolved_path(*, path_value):
    selected_path = Path(path_value).expanduser()
    if not selected_path.is_absolute():
        selected_path = REPOSITORY_ROOT / selected_path
    return selected_path.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", default="data/markdown_db")
    parser.add_argument(
        "--output-root", default="data/markdown_db/metadata/topic_graph"
    )
    parser.add_argument(
        "--extraction-mode", choices=["langextract", "rule-based"],
        default="langextract",
    )
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--topic-count", type=int, default=20)
    parser.add_argument("--random-seed", type=int, default=1729)
    parser.add_argument("--minimum-document-frequency", type=int, default=10)
    parser.add_argument("--maximum-document-fraction", type=float, default=0.8)
    parser.add_argument("--anchor-strength", type=float, default=3.0)
    parser.add_argument("--assignment-threshold", type=float, default=0.9)
    parser.add_argument("--maximum-topics-per-block", type=int, default=3)
    arguments = parser.parse_args()

    environment_path = REPOSITORY_ROOT / ".env"
    if environment_path.is_file():
        load_dotenv(dotenv_path=environment_path, override=False)
    try:
        if arguments.topic_count < 1:
            raise ValueError("topic count must be positive")
        if arguments.minimum_document_frequency < 1:
            raise ValueError("minimum document frequency must be positive")
        if not 0 < arguments.maximum_document_fraction <= 1:
            raise ValueError("maximum document fraction must be in (0, 1]")
        if not 0 < arguments.assignment_threshold < 1:
            raise ValueError("assignment threshold must be in (0, 1)")
        if arguments.maximum_topics_per_block < 1:
            raise ValueError("maximum topics per block must be positive")
        result = run_topic_pipeline(
            markdown_db_path=_resolved_path(path_value=arguments.markdown_db),
            output_root=_resolved_path(path_value=arguments.output_root),
            browser_base_url=os.getenv(
                "COMMENT_BROWSER_BASE_URL", "http://127.0.0.1:8765"
            ),
            extraction_mode=arguments.extraction_mode,
            model_id=arguments.model,
            api_key=os.getenv("LANGEXTRACT_API_KEY") or os.getenv("GEMINI_API_KEY"),
            topic_count=arguments.topic_count,
            random_seed=arguments.random_seed,
            minimum_document_frequency=arguments.minimum_document_frequency,
            maximum_document_fraction=arguments.maximum_document_fraction,
            anchor_strength=arguments.anchor_strength,
            assignment_threshold=arguments.assignment_threshold,
            maximum_topics_per_block=arguments.maximum_topics_per_block,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"topic_pipeline.py Error: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()