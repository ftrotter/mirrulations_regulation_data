"""Pretty-print verified downloaded JSON while retaining byte provenance."""

import json

from .inventory import inventory_fingerprint, inventory_source, sha256_file


def normalize_json_sources(*, source_root, docket_id, verification_manifest_path):
    manifest = json.loads(verification_manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("verified") or manifest.get("docket_id") != docket_id:
        raise ValueError(
            "json_normalization.py Error: matching successful verification is required"
        )
    if manifest.get("json_normalized_in_place"):
        raise ValueError(
            "json_normalization.py Error: JSON was already normalized for this "
            "verified acquisition; use a fresh verified acquisition to normalize again"
        )
    records = []
    for json_path in sorted(source_root.rglob("*.json")):
        if docket_id not in json_path.relative_to(source_root).parts:
            continue
        original_hash = sha256_file(file_path=json_path)
        try:
            value = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            records.append({
                "source_object_key": json_path.relative_to(source_root).as_posix(),
                "status": "failed", "original_sha256": original_hash,
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        pretty_text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        json_path.write_text(pretty_text, encoding="utf-8")
        records.append({
            "source_object_key": json_path.relative_to(source_root).as_posix(),
            "status": "normalized", "original_sha256": original_hash,
            "normalized_sha256": sha256_file(file_path=json_path),
            "method": "json.dumps(indent=2, sort_keys=True, ensure_ascii=False)",
        })
    if any(record["status"] == "failed" for record in records):
        raise ValueError("json_normalization.py Error: one or more JSON files failed")
    assets = inventory_source(source_root=source_root, docket_id=docket_id)
    manifest["local_source_inventory_fingerprint"] = inventory_fingerprint(assets=assets)
    manifest["json_normalized_in_place"] = True
    verification_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"schema_version": 1, "docket_id": docket_id, "records": records}