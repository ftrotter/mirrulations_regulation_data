#!/usr/bin/env python3
"""Capture, compare, or summarize Markdown corpus validation state."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.validation import (  # noqa: E402
    capture_tree_hashes,
    compare_tree_hashes,
    corpus_summary,
    read_hash_snapshot,
    write_hash_snapshot,
)


def create_argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--markdown-db", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--compare")
    parser.add_argument("--primary-source-object-key")
    return parser


def main():
    arguments = create_argument_parser().parse_args()
    source_root = Path(arguments.source_root).expanduser().resolve()
    markdown_db_path = Path(arguments.markdown_db).expanduser().resolve()
    try:
        current_hashes = capture_tree_hashes(
            source_root=source_root, markdown_db_path=markdown_db_path
        )
        if arguments.snapshot:
            write_hash_snapshot(
                output_path=Path(arguments.snapshot).expanduser().resolve(),
                tree_hashes=current_hashes,
            )
        if arguments.compare:
            previous_hashes = read_hash_snapshot(
                snapshot_path=Path(arguments.compare).expanduser().resolve()
            )
            changed_trees = compare_tree_hashes(
                before_hashes=previous_hashes, after_hashes=current_hashes
            )
            if changed_trees:
                raise ValueError(
                    "validate_markdown_corpus.py Error: changed trees: "
                    + ", ".join(changed_trees)
                )
        summary = corpus_summary(
            markdown_db_path=markdown_db_path,
            primary_source_object_key=arguments.primary_source_object_key,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"tree_hashes": current_hashes, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()