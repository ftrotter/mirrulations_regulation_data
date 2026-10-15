#!/usr/bin/env python3
"""Validate or import a file-backed graph bundle into local Neo4j."""

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.graph_io import (  # noqa: E402
    import_graph_bundle,
    load_graph_bundle,
)


def _resolved_path(*, path_value):
    selected_path = Path(path_value).expanduser()
    if not selected_path.is_absolute():
        selected_path = REPOSITORY_ROOT / selected_path
    return selected_path.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "import"])
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--uri")
    parser.add_argument("--user")
    arguments = parser.parse_args()

    environment_path = REPOSITORY_ROOT / ".env"
    if environment_path.is_file():
        load_dotenv(dotenv_path=environment_path, override=False)

    try:
        bundle_path = _resolved_path(path_value=arguments.bundle)
        bundle = load_graph_bundle(bundle_path=bundle_path)
        if arguments.command == "validate":
            print(
                f"Validated {len(bundle.nodes)} nodes and "
                f"{len(bundle.relationships)} relationships in {bundle_path}"
            )
            return

        uri = arguments.uri or os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = arguments.user or os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        if not password:
            raise ValueError("NEO4J_PASSWORD is not set")
        try:
            from neo4j import GraphDatabase
        except ImportError as error:
            raise ValueError(
                "install requirements.txt before importing into Neo4j"
            ) from error
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            driver.verify_connectivity()
            import_graph_bundle(bundle=bundle, driver=driver)
        finally:
            driver.close()
        print(
            f"Imported {len(bundle.nodes)} nodes and "
            f"{len(bundle.relationships)} relationships into {uri}"
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"neo4j_graph.py Error: {error}\n")


if __name__ == "__main__":
    main()