#!/usr/bin/env python3
"""Add explicitly selected public source objects as a regression case."""

import argparse
import hashlib
from pathlib import Path
import shutil

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "regression_cases"


def sha256_file(*, file_path):
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--case-type", required=True)
    parser.add_argument("--docket-id", required=True)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--canonical-source", required=True)
    parser.add_argument("--structural-source", action="append", default=[])
    arguments = parser.parse_args()
    case_root = FIXTURE_ROOT / arguments.case_id
    if case_root.exists():
        parser.exit(1, f"add_regression_fixture.py Error: case exists: {case_root}\n")
    source_root = case_root / "source"
    source_root.mkdir(parents=True)

    def copy_record(source_value, role):
        source_path = Path(source_value).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError(f"source does not exist: {source_path}")
        destination = source_root / source_path.name
        shutil.copy2(source_path, destination)
        return {
            "path": f"source/{destination.name}",
            "role": role,
            "sha256": sha256_file(file_path=destination),
            "mirrulations_object_key": (
                source_path.relative_to(REPOSITORY_ROOT / "data" / "source" / "mirrulations").as_posix()
                if (REPOSITORY_ROOT / "data" / "source" / "mirrulations") in source_path.parents
                else None
            ),
        }

    try:
        canonical = copy_record(arguments.canonical_source, "canonical_text")
        structural = [
            copy_record(value, "structural_source")
            for value in arguments.structural_source
        ]
    except ValueError as error:
        shutil.rmtree(case_root, ignore_errors=True)
        parser.exit(1, f"add_regression_fixture.py Error: {error}\n")
    manifest = {
        "schema_version": 1,
        "case_id": arguments.case_id,
        "case_type": arguments.case_type,
        "description": arguments.description,
        "public_source": {
            "docket_id": arguments.docket_id,
            "record_id": arguments.record_id,
            "regulations_gov_url": f"https://www.regulations.gov/comment/{arguments.record_id}",
            "public_record_notice": True,
        },
        "canonical_source": canonical,
        "structural_sources": structural,
        "expected": {
            "comparison_mode": "structural",
            "forbidden_patterns": ["<br", "</br>", "\\x00", '<a id="p-'],
            "required_patterns": [],
        },
    }
    (case_root / "case.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"Added regression case: {case_root}")


if __name__ == "__main__":
    main()