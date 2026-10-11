"""Configuration and path-safety rules for the Markdown pipeline."""

import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKDOWN_DB_PATH = REPOSITORY_ROOT / "data" / "markdown_db"


def _resolved_path(*, path_value):
    return Path(path_value).expanduser().resolve()


def validate_separate_roots(*, source_root, markdown_db_path):
    """Reject equal or nested source and generated-data roots."""
    resolved_source_root = _resolved_path(path_value=source_root)
    resolved_markdown_db_path = _resolved_path(path_value=markdown_db_path)
    if (
        resolved_source_root == resolved_markdown_db_path
        or resolved_source_root in resolved_markdown_db_path.parents
        or resolved_markdown_db_path in resolved_source_root.parents
    ):
        raise ValueError(
            "configuration.py Error: MIRRULATIONS_DESTINATION_PATH and "
            "MARKDOWN_DB_PATH must be separate, non-overlapping directories"
        )
    return resolved_source_root, resolved_markdown_db_path


def load_paths(*, source_root=None, markdown_db_path=None):
    """Resolve configured roots without reading or modifying an .env file."""
    selected_source_root = source_root or os.getenv("MIRRULATIONS_DESTINATION_PATH")
    if not selected_source_root:
        raise ValueError(
            "configuration.py Error: MIRRULATIONS_DESTINATION_PATH is not set"
        )
    selected_markdown_db_path = (
        markdown_db_path
        or os.getenv("MARKDOWN_DB_PATH")
        or DEFAULT_MARKDOWN_DB_PATH
    )
    resolved_source_root, resolved_markdown_db_path = validate_separate_roots(
        source_root=selected_source_root,
        markdown_db_path=selected_markdown_db_path,
    )
    if not resolved_source_root.is_dir():
        raise ValueError(
            f"configuration.py Error: source mirror does not exist: "
            f"{resolved_source_root}"
        )
    return resolved_source_root, resolved_markdown_db_path