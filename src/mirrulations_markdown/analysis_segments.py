"""Plan coherent, bounded LLM analysis segments from semantic blocks."""

import hashlib


ANALYZABLE_TYPES = {"paragraph", "list", "quotation", "table"}


def _segment_id(*, owned_block_ids):
    identity = "|".join(owned_block_ids)
    return "segment-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def _chunks(*, blocks, maximum_owned_blocks, maximum_characters):
    chunks = []
    current = []
    current_characters = 0
    for block in blocks:
        block_characters = len(block["plain_text"])
        if current and (
            len(current) >= maximum_owned_blocks
            or current_characters + block_characters > maximum_characters
        ):
            chunks.append(current)
            current = []
            current_characters = 0
        current.append(block)
        current_characters += block_characters
    if current:
        chunks.append(current)
    return chunks


def build_analysis_segments(
    *, blocks, maximum_owned_blocks=20, maximum_characters=20000,
    unstructured_owned_blocks=10
):
    """Return section-aware segments with explicit ownership and context overlap."""
    substantive = [
        block for block in blocks
        if block["block_type"] in ANALYZABLE_TYPES
        or block["block_type"] in {"section", "label"}
    ]
    groups = []
    current_group = []
    has_sections = any(block["block_type"] == "section" for block in substantive)
    for block in substantive:
        if block["block_type"] == "section" and current_group:
            groups.append(current_group)
            current_group = []
        current_group.append(block)
    if current_group:
        groups.append(current_group)
    if not has_sections:
        groups = [substantive]

    planned_chunks = []
    for group in groups:
        heading = group[0] if group and group[0]["block_type"] == "section" else None
        analyzable = [block for block in group if block["block_type"] in ANALYZABLE_TYPES]
        chunk_size = maximum_owned_blocks if heading else unstructured_owned_blocks
        for chunk_number, chunk in enumerate(_chunks(
            blocks=analyzable, maximum_owned_blocks=chunk_size,
            maximum_characters=maximum_characters,
        )):
            if chunk:
                planned_chunks.append({
                    "heading": heading, "owned": chunk,
                    "owns_section_summary": chunk_number == 0,
                })

    all_context_blocks = [
        block for block in substantive if block["block_type"] != "section"
    ]
    all_analyzable = [
        block for block in all_context_blocks if block["block_type"] in ANALYZABLE_TYPES
    ]
    index_by_id = {block["block_id"]: index for index, block in enumerate(all_analyzable)}
    context_index_by_id = {
        block["block_id"]: index for index, block in enumerate(all_context_blocks)
    }
    segments = []
    for chunk in planned_chunks:
        owned = chunk["owned"]
        first_index = index_by_id[owned[0]["block_id"]]
        last_index = index_by_id[owned[-1]["block_id"]]
        previous_owned_neighbor = all_analyzable[first_index - 1] if first_index > 0 else None
        next_owned_neighbor = (
            all_analyzable[last_index + 1]
            if last_index + 1 < len(all_analyzable) else None
        )
        context_start = context_index_by_id[owned[0]["block_id"]]
        context_end = context_index_by_id[owned[-1]["block_id"]]
        if previous_owned_neighbor:
            context_start = context_index_by_id[previous_owned_neighbor["block_id"]]
        if next_owned_neighbor:
            context_end = context_index_by_id[next_owned_neighbor["block_id"]]
        heading = chunk["heading"]
        owned_ids = [block["block_id"] for block in owned]
        owned_id_set = set(owned_ids)
        segment_blocks = [
            {
                **block,
                "analysis_role": (
                    "owned" if block["block_id"] in owned_id_set else "context_only"
                ),
            }
            for block in all_context_blocks[context_start : context_end + 1]
        ]
        segments.append({
            "segment_id": _segment_id(owned_block_ids=owned_ids),
            "section_block_id": (
                heading["block_id"]
                if heading and chunk["owns_section_summary"] else None
            ),
            "section_heading": heading["plain_text"] if heading else None,
            "owned_block_ids": owned_ids,
            "blocks": segment_blocks,
        })
    return segments