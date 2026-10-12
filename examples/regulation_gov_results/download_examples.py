#!/usr/bin/env python3
"""Redownload the Regulations.gov examples listed in results/manifest.json."""

import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.regulations.gov/v4"
EXAMPLE_DIRECTORY = Path(__file__).resolve().parent
EXAMPLE_MANIFEST = EXAMPLE_DIRECTORY / "results" / "manifest.json"


def download_json(*, api_key, resource_path, parameters=None):
    """Download one JSON response using the API key required by Regulations.gov."""
    query = urlencode(parameters or {})
    url = f"{API_ROOT}/{resource_path}"
    if query:
        url = f"{url}?{query}"
    request = Request(url, headers={"X-Api-Key": api_key})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def write_json(*, path, value):
    """Write pretty-printed JSON so the downloaded examples are easy to browse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_dotenv(*, dotenv_path):
    """Load a simple ignored dotenv file without requiring a third-party package."""
    if dotenv_path is None:
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue
        name, value = stripped_line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=EXAMPLE_DIRECTORY / "results",
        help="Where to write JSON (default: this example's results directory).",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        help="Optional ignored dotenv file containing REGULATIONS_GOV_API_KEY.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.5,
        help="Delay after each request so the example is polite to the API.",
    )
    arguments = parser.parse_args()

    load_dotenv(dotenv_path=arguments.dotenv)
    api_key = os.getenv("REGULATIONS_GOV_API_KEY")
    if not api_key:
        parser.error("REGULATIONS_GOV_API_KEY is not set")
    if arguments.pause_seconds < 0:
        parser.error("--pause-seconds cannot be negative")

    # This checked-in manifest is the hard-coded selection of examples. The
    # script does not perform a broad search that might select different data.
    manifest = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))
    document_ids = {
        document_id
        for category in manifest["categories"]
        for document_id in category["document_ids"]
    }
    output_directory = arguments.output_directory.resolve()
    seen_docket_ids = set()
    seen_comment_ids = set()

    for document_id in sorted(document_ids):
        print(f"Downloading document {document_id}")
        document_response = download_json(
            api_key=api_key,
            resource_path=f"documents/{document_id}",
        )
        write_json(
            path=output_directory / "documents" / f"{document_id}.json",
            value=document_response,
        )
        time.sleep(arguments.pause_seconds)

        attributes = document_response["data"]["attributes"]

        # docketId is the direct document-to-docket join.
        docket_id = attributes.get("docketId")
        if docket_id and docket_id not in seen_docket_ids:
            docket_response = download_json(
                api_key=api_key,
                resource_path=f"dockets/{docket_id}",
            )
            write_json(
                path=output_directory / "dockets" / f"{docket_id}.json",
                value=docket_response,
            )
            seen_docket_ids.add(docket_id)
            time.sleep(arguments.pause_seconds)

        # This is the easy-to-miss Regulations.gov join. The comments search
        # expects the document's opaque objectId, not its public document ID.
        object_id = attributes.get("objectId")
        if not object_id:
            continue
        comment_search = download_json(
            api_key=api_key,
            resource_path="comments",
            parameters={
                "filter[commentOnId]": object_id,
                "page[size]": 5,
                "sort": "postedDate",
            },
        )
        time.sleep(arguments.pause_seconds)

        # Only comment metadata is downloaded. The example intentionally does
        # not retrieve comment attachments or any other binary content.
        for comment_summary in comment_search.get("data", []):
            comment_id = comment_summary["id"]
            if comment_id in seen_comment_ids:
                continue
            comment_response = download_json(
                api_key=api_key,
                resource_path=f"comments/{comment_id}",
            )
            write_json(
                path=output_directory / "comments" / f"{comment_id}.json",
                value=comment_response,
            )
            seen_comment_ids.add(comment_id)
            time.sleep(arguments.pause_seconds)

    # Copy the hard-coded selection into alternate output directories too, so
    # a temporary redownload remains self-describing when shared or inspected.
    write_json(path=output_directory / "manifest.json", value=manifest)
    print(f"Finished. Results are in {output_directory}")


if __name__ == "__main__":
    main()