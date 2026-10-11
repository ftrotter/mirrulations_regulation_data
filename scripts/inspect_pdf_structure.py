#!/usr/bin/env python3
"""Print a concise JSON summary of pypdf structure extraction."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.pdf_structure import extract_pdf_structure  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("--paragraph-limit", type=int, default=20)
    arguments = parser.parse_args()
    structure = extract_pdf_structure(
        pdf_path=Path(arguments.pdf_path).expanduser().resolve()
    )
    paragraphs = []
    for page in structure["pages"]:
        for paragraph in page["paragraphs"]:
            paragraphs.append(
                {"page_number": page["page_number"], **paragraph}
            )
    output = {
        "parser": structure["parser"],
        "parser_version": structure["parser_version"],
        "page_count": structure["page_count"],
        "line_count": sum(len(page["lines"]) for page in structure["pages"]),
        "paragraph_count": len(paragraphs),
        "paragraph_sample": paragraphs[: arguments.paragraph_limit],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()