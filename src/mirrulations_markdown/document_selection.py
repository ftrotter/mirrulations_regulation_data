"""Select readable logical documents from an exact source-asset inventory."""

import json
from pathlib import Path


def _json_body_location(*, source_path):
    try:
        value = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    data = value.get("data") if isinstance(value, dict) else None
    attributes = data.get("attributes") if isinstance(data, dict) else None
    if not isinstance(attributes, dict):
        return None
    comment = attributes.get("comment")
    if isinstance(comment, str) and comment.strip():
        return "data.attributes.comment"
    return None


def select_logical_documents(*, source_root, assets):
    """Return selected readable assets and an auditable decision per asset."""
    selected_assets = []
    decisions = []
    for asset in assets:
        source_key = asset["source_object_key"]
        suffix = asset["source_suffix"]
        selected = False
        reason = None
        content_location = None
        if asset["source_role"] == "structural-source":
            reason = "structural-source-only"
        elif suffix in {".htm", ".html", ".txt"}:
            selected = True
            reason = "readable-text-representation"
        elif suffix == ".json":
            content_location = _json_body_location(
                source_path=source_root / source_key
            )
            if content_location:
                selected = True
                reason = "form-submitted-comment-body"
            else:
                reason = "metadata-only-json"
        else:
            reason = "unsupported-readable-representation"
        decision = {
            "source_object_key": source_key,
            "source_sha256": asset["source_sha256"],
            "selected_for_markdown": selected,
            "selection_reason": reason,
            "content_location": content_location,
            "markdown_path": asset["markdown_path"] if selected else None,
        }
        decisions.append(decision)
        if selected:
            selected_asset = dict(asset)
            selected_asset["selection_reason"] = reason
            selected_asset["content_location"] = content_location
            selected_assets.append(selected_asset)
    return selected_assets, decisions