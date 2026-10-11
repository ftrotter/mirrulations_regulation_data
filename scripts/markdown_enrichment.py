#!/usr/bin/env python3
"""Create initial and citation-enriched Markdown from a verified mirror."""

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.configuration import load_paths  # noqa: E402
from mirrulations_markdown.pipeline import MarkdownPipeline  # noqa: E402
from mirrulations_markdown.verification import (  # noqa: E402
    require_verified_manifest,
    verify_docket,
)


def create_argument_parser():
    parser = argparse.ArgumentParser(
        description="Create reproducible Markdown stages from a Mirrulations text mirror."
    )
    parser.add_argument("--source-root", help="Override MIRRULATIONS_DESTINATION_PATH.")
    parser.add_argument("--markdown-db", help="Override MARKDOWN_DB_PATH.")
    parser.add_argument("--docket", required=True, help="Bounded docket ID.")
    parser.add_argument("--rclone-config", help="Required when --verify is used.")
    parser.add_argument("--verify", action="store_true", help="Run rclone checks first.")
    parser.add_argument("--verification-manifest", help="Existing successful manifest.")
    return parser


def main():
    parser = create_argument_parser()
    arguments = parser.parse_args()
    try:
        source_root, markdown_db_path = load_paths(
            source_root=arguments.source_root,
            markdown_db_path=arguments.markdown_db,
        )
        metadata_root = markdown_db_path / "metadata"
        if arguments.verify:
            if not arguments.rclone_config:
                raise ValueError("--rclone-config is required with --verify")
            manifest_path, _manifest = verify_docket(
                source_root=source_root,
                metadata_root=metadata_root,
                docket_id=arguments.docket,
                rclone_config_file=Path(arguments.rclone_config).expanduser().resolve(),
            )
        else:
            manifest_path = (
                Path(arguments.verification_manifest).expanduser().resolve()
                if arguments.verification_manifest
                else metadata_root
                / "manifests"
                / "verification"
                / f"{arguments.docket}.json"
            )
        require_verified_manifest(
            manifest_path=manifest_path,
            source_root=source_root,
            docket_id=arguments.docket,
        )
        run_status = MarkdownPipeline.run(
            source_root=source_root,
            markdown_db_path=markdown_db_path,
            docket_id=arguments.docket,
        )
    except ValueError as error:
        parser.exit(1, f"markdown_enrichment.py Error: {error}\n")
    print(
        f"Processed {run_status['completed_asset_count']} of "
        f"{run_status['markdown_asset_count']} readable assets from "
        f"{run_status['source_asset_count']} total source objects."
    )
    if run_status["failed_asset_count"]:
        parser.exit(1, "markdown_enrichment.py Error: requested work is incomplete\n")


if __name__ == "__main__":
    main()