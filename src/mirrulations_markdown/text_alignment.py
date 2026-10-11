"""Align PDF paragraph evidence to canonical extracted text offsets."""

import re


def normalized_text_with_offsets(*, text):
    """Collapse whitespace while mapping normalized characters to source offsets."""
    normalized_characters = []
    source_offsets = []
    pending_space_offset = None
    for source_offset, character in enumerate(text):
        if character.isspace():
            if normalized_characters and pending_space_offset is None:
                pending_space_offset = source_offset
            continue
        if pending_space_offset is not None:
            normalized_characters.append(" ")
            source_offsets.append(pending_space_offset)
            pending_space_offset = None
        normalized_characters.append(character)
        source_offsets.append(source_offset)
    return "".join(normalized_characters), source_offsets


def _block_type(*, text, line_count):
    stripped_text = text.strip()
    if line_count <= 2 and re.match(
        r"^(?:[IVXLCDM]+\.|\d+(?:\.\d+)*\.?|[A-Z]\.)\s+\S+",
        stripped_text,
    ):
        return "heading"
    return "paragraph"


def align_pdf_paragraphs(*, canonical_text, pdf_structure):
    """Project exact whitespace-normalized PDF paragraphs onto canonical text."""
    normalized_canonical, canonical_offsets = normalized_text_with_offsets(
        text=canonical_text
    )
    search_offset = 0
    aligned_blocks = []
    warnings = []
    for page in pdf_structure["pages"]:
        for paragraph in page["paragraphs"]:
            normalized_paragraph, _offsets = normalized_text_with_offsets(
                text=paragraph["text"]
            )
            if not normalized_paragraph:
                continue
            match_start = normalized_canonical.find(normalized_paragraph, search_offset)
            if match_start < 0:
                # Repeated headers can occur before the current body cursor. They
                # are retained as unmatched structural evidence, not invented text.
                warnings.append(
                    {
                        "page_number": page["page_number"],
                        "paragraph_text": paragraph["text"],
                        "warning": "exact_canonical_match_not_found",
                    }
                )
                continue
            match_end = match_start + len(normalized_paragraph)
            source_start = canonical_offsets[match_start]
            source_end = canonical_offsets[match_end - 1] + 1
            canonical_block_text = re.sub(
                r"\s+", " ", canonical_text[source_start:source_end]
            ).strip()
            aligned_blocks.append(
                {
                    "block_type": _block_type(
                        text=canonical_block_text,
                        line_count=paragraph["line_count"],
                    ),
                    "plain_text": canonical_block_text,
                    "source_start": source_start,
                    "source_end": source_end,
                    "page_start": page["page_number"],
                    "page_end": page["page_number"],
                    "alignment_method": "exact_whitespace_normalized",
                    "alignment_confidence": 1.0,
                }
            )
            search_offset = match_end
    blocks_with_gaps = []
    previous_end = 0
    for block in aligned_blocks:
        unmatched_gap = canonical_text[previous_end:block["source_start"]]
        if unmatched_gap.strip():
            gap_text = re.sub(r"\s+", " ", unmatched_gap).strip()
            warnings.append(
                {
                    "source_start": previous_end,
                    "source_end": block["source_start"],
                    "warning": "unmatched_canonical_gap",
                }
            )
            blocks_with_gaps.append(
                {
                    "block_type": "unmatched-canonical",
                    "plain_text": gap_text,
                    "source_start": previous_end,
                    "source_end": block["source_start"],
                    "page_start": block["page_start"],
                    "page_end": block["page_start"],
                    "alignment_method": "canonical_gap_preserved",
                    "alignment_confidence": 0.0,
                }
            )
        blocks_with_gaps.append(block)
        previous_end = block["source_end"]
    if canonical_text[previous_end:].strip():
        suffix_text = re.sub(r"\s+", " ", canonical_text[previous_end:]).strip()
        warnings.append(
            {
                "source_start": previous_end,
                "source_end": len(canonical_text),
                "warning": "unmatched_canonical_suffix",
            }
        )
        final_page = aligned_blocks[-1]["page_end"] if aligned_blocks else None
        blocks_with_gaps.append(
            {
                "block_type": "unmatched-canonical",
                "plain_text": suffix_text,
                "source_start": previous_end,
                "source_end": len(canonical_text),
                "page_start": final_page,
                "page_end": final_page,
                "alignment_method": "canonical_gap_preserved",
                "alignment_confidence": 0.0,
            }
        )
    return {
        "parser": pdf_structure.get("parser"),
        "parser_version": pdf_structure.get("parser_version"),
        "page_count": pdf_structure.get("page_count"),
        "parser_warnings": pdf_structure.get("warnings", []),
        "blocks": blocks_with_gaps,
        "warnings": warnings,
    }