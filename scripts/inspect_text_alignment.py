#!/usr/bin/env python3
"""Inspect PDF paragraph alignment against canonical Mirrulations text."""

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.pdf_structure import extract_pdf_structure  # noqa: E402
from mirrulations_markdown.text_alignment import align_pdf_paragraphs  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canonical_text_path")
    parser.add_argument("pdf_path")
    parser.add_argument("--block-limit", type=int, default=20)
    arguments = parser.parse_args()
    canonical_path = Path(arguments.canonical_text_path).expanduser().resolve()
    pdf_path = Path(arguments.pdf_path).expanduser().resolve()
    canonical_text = canonical_path.read_text(encoding="utf-8", errors="replace")
    structure = extract_pdf_structure(pdf_path=pdf_path)
    alignment = align_pdf_paragraphs(
        canonical_text=canonical_text, pdf_structure=structure
    )
    covered_characters = sum(
        block["source_end"] - block["source_start"]
        for block in alignment["blocks"]
    )
    output = {
        "canonical_characters": len(canonical_text),
        "aligned_characters": covered_characters,
        "coverage": covered_characters / len(canonical_text) if canonical_text else 1.0,
        "aligned_blocks": len(alignment["blocks"]),
        "warning_count": len(alignment["warnings"]),
        "block_sample": alignment["blocks"][: arguments.block_limit],
        "warning_sample": alignment["warnings"][: arguments.block_limit],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()