"""Revision-aware index of mirrored Regulations.gov JSON resources."""

import hashlib
import json
from pathlib import Path
import re


REVISION_PATTERN = re.compile(r"^(?P<stem>.+?)(?:\((?P<revision>\d+)\))?\.json$")


def _revision_number(*, path):
    match = REVISION_PATTERN.match(path.name)
    return int(match.group("revision")) if match and match.group("revision") else 0


def _field_presence(*, attributes):
    return {
        field: ("explicit-null" if value is None else "present")
        for field, value in attributes.items()
    }


def build_resource_index(*, source_root, assets=None):
    """Index every API JSON version and select the highest mirrored revision."""
    hashes_by_key = {
        asset["source_object_key"]: asset["source_sha256"] for asset in (assets or [])
    }
    versions_by_identity = {}
    for json_path in sorted(source_root.rglob("*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("id") or not data.get("type"):
            continue
        attributes = data.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        source_object_key = json_path.relative_to(source_root).as_posix()
        source_sha256 = hashes_by_key.get(source_object_key)
        if source_sha256 is None:
            source_sha256 = hashlib.sha256(json_path.read_bytes()).hexdigest()
        record = {
            "resource_type": data["type"],
            "public_id": data["id"],
            "object_id": attributes.get("objectId"),
            "docket_id": attributes.get("docketId"),
            "source_object_key": source_object_key,
            "source_sha256": source_sha256,
            "revision_number": _revision_number(path=json_path),
            "attributes": attributes,
            "attribute_presence": _field_presence(attributes=attributes),
        }
        identity = (data["type"], data["id"])
        versions_by_identity.setdefault(identity, []).append(record)

    resources = []
    current_by_identity = {}
    for identity, versions in sorted(versions_by_identity.items()):
        ordered_versions = sorted(
            versions,
            key=lambda item: (item["revision_number"], item["source_object_key"]),
        )
        maximum_revision = ordered_versions[-1]["revision_number"]
        current_candidates = [
            item for item in ordered_versions if item["revision_number"] == maximum_revision
        ]
        if len(current_candidates) != 1:
            raise ValueError(
                "resource_index.py Error: ambiguous current revision for "
                f"{identity[0]} {identity[1]}"
            )
        current = current_candidates[0]
        current_by_identity[identity] = current
        resources.append({
            "resource_type": identity[0],
            "public_id": identity[1],
            "selection_policy": "highest-revision-suffix",
            "current_source_object_key": current["source_object_key"],
            "current_revision_number": current["revision_number"],
            "versions": ordered_versions,
        })
    return {"resources": resources, "current_by_identity": current_by_identity}


def current_resource(*, resource_index, resource_type, public_id, docket_id=None):
    record = resource_index["current_by_identity"].get((resource_type, public_id))
    if record is None:
        return None
    if docket_id is not None and record.get("docket_id") != docket_id:
        raise ValueError(
            "resource_index.py Error: resource docket does not match expected docket: "
            f"{public_id}"
        )
    return record