#!/usr/bin/env python3
"""Collect Regulations.gov lifecycle metadata evidence."""

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.regulations_gov_research import RegulationsGovResearch  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default="data/regulations_gov_research")
    parser.add_argument("--dotenv")
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--search-size", type=int, default=100)
    parser.add_argument("--requests-per-second", type=float, default=2.0)
    arguments = parser.parse_args()
    try:
        if arguments.dotenv:
            load_dotenv(Path(arguments.dotenv).expanduser().resolve(), override=False)
        if arguments.sample_size < 1 or not 1 <= arguments.search_size <= 250:
            raise ValueError("sample-size must be positive and search-size must be 1 through 250")
        result = RegulationsGovResearch.collect(
            output_root=Path(arguments.output_root).expanduser().resolve(),
            sample_size=arguments.sample_size, search_size=arguments.search_size,
            requests_per_second=arguments.requests_per_second,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"regulations_gov_research.py Error: {error}\n")
    print(json.dumps({
        item["category_key"]: item["accepted_sample_size"]
        for item in result["evidence"]
    }, indent=2))


if __name__ == "__main__":
    main()