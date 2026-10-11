"""Non-mutating rclone verification for a bounded text-only docket mirror."""

import datetime
import json
import subprocess

from .inventory import inventory_fingerprint, inventory_source


REMOTE = "myconfig:mirrulations/"


def docket_include_patterns(*, docket_id, text_only=False):
    agency = docket_id.split("-", 1)[0]
    if not agency or docket_id.count("-") < 2:
        raise ValueError(
            f"verification.py Error: invalid docket ID {docket_id!r}"
        )
    if text_only:
        suffixes = ("*.txt", "*.json", "*.htm", "*.html")
        return [
            f"/{data_root}/{agency}/{docket_id}/**/{suffix}"
            for data_root in ("raw-data", "derived-data")
            for suffix in suffixes
        ]
    return [
        f"/{data_root}/{agency}/{docket_id}/**/*"
        for data_root in ("raw-data", "derived-data")
    ]


def build_check_command(
    *, source, destination, rclone_config_file, include_patterns, combined_path
):
    command = [
        "rclone", "check", source, destination, "--config",
        str(rclone_config_file), "--combined", str(combined_path),
    ]
    for include_pattern in include_patterns:
        command.extend(("--include", include_pattern))
    return command


def _comparison_counts(*, combined_path):
    counts = {"matching": 0, "missing": 0, "differing": 0, "unexpected": 0}
    if not combined_path.is_file():
        return counts
    # rclone combined output uses '-' for source-only (missing locally) and '+'
    # for destination-only (unexpected locally).
    symbol_names = {"=": "matching", "-": "missing", "*": "differing", "+": "unexpected"}
    for line in combined_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and line[0] in symbol_names:
            counts[symbol_names[line[0]]] += 1
    return counts


def verify_docket(*, source_root, metadata_root, docket_id, rclone_config_file):
    """Compare the selected remote and local trees and persist the result."""
    verification_root = metadata_root / "manifests" / "verification"
    verification_root.mkdir(parents=True, exist_ok=True)
    remote_report = verification_root / f"{docket_id}_remote_to_local.txt"
    include_patterns = docket_include_patterns(docket_id=docket_id)
    commands = [build_check_command(
        source=REMOTE,
        destination=str(source_root),
        rclone_config_file=rclone_config_file,
        include_patterns=include_patterns,
        combined_path=remote_report,
    )]
    errors = []
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise ValueError(
                "verification.py Error: rclone executable was not found"
            ) from error
        except subprocess.CalledProcessError as error:
            errors.append(
                f"rclone exit {error.returncode}: {(error.stderr or error.stdout).strip()}"
            )
    remote_counts = _comparison_counts(combined_path=remote_report)
    counts = remote_counts
    selected_assets = inventory_source(source_root=source_root, docket_id=docket_id)
    if not selected_assets:
        errors.append("verification.py Error: selected docket has no local text assets")
    verified = not errors and not any(
        counts[name] for name in ("missing", "differing", "unexpected")
    )
    manifest = {
        "schema_version": 1,
        "verified": verified,
        "docket_id": docket_id,
        "text_only": False,
        "source_root": str(source_root.resolve()),
        "remote": REMOTE,
        "include_patterns": include_patterns,
        "commands": commands,
        "verified_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "counts": counts,
        "selected_asset_count": len(selected_assets),
        "source_inventory_fingerprint": inventory_fingerprint(assets=selected_assets),
        "errors": errors,
    }
    manifest_path = verification_root / f"{docket_id}.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path, manifest


def require_verified_manifest(*, manifest_path, source_root, docket_id=None):
    if not manifest_path or not manifest_path.is_file():
        raise ValueError(
            "verification.py Error: a successful verification manifest is required"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("verified"):
        raise ValueError("verification.py Error: source mirror is not verified")
    if manifest.get("text_only"):
        raise ValueError(
            "verification.py Error: text-only verification is insufficient for "
            "structure-aware Markdown"
        )
    if manifest.get("source_root") != str(source_root.resolve()):
        raise ValueError(
            "verification.py Error: verification manifest belongs to another source root"
        )
    manifest_docket_id = manifest.get("docket_id")
    if not manifest_docket_id:
        raise ValueError("verification.py Error: manifest has no docket scope")
    if docket_id and manifest_docket_id != docket_id:
        raise ValueError(
            "verification.py Error: verification manifest belongs to another docket"
        )
    current_assets = inventory_source(
        source_root=source_root, docket_id=manifest_docket_id
    )
    current_fingerprint = inventory_fingerprint(assets=current_assets)
    expected_local_fingerprint = manifest.get(
        "local_source_inventory_fingerprint",
        manifest.get("source_inventory_fingerprint"),
    )
    if expected_local_fingerprint != current_fingerprint:
        raise ValueError(
            "verification.py Error: selected source bytes changed after verification"
        )
    return manifest