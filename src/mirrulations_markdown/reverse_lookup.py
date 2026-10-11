"""Generate the global citation-to-document paragraph lookup."""

from pathlib import Path


def write_citation_reverse_lookup(
    *, output_path, citations, reference_names, document_names
):
    occurrences = {}
    for citation in citations:
        target = citation["normalized_target"]
        occurrence = (
            citation["markdown_path"], citation["block_id"]
        )
        occurrences.setdefault(target, set()).add(occurrence)
    lines = ["# Citation Reverse Lookup", ""]
    for target in sorted(occurrences, key=lambda item: reference_names.get(item, item)):
        lines.extend((f"## {reference_names.get(target, target)}", ""))
        for markdown_path, block_id in sorted(occurrences[target]):
            document_name = document_names.get(markdown_path, Path(markdown_path).stem)
            link = f"../stage002_addition_of_citations/{markdown_path}#{block_id}"
            lines.append(f"- [{document_name}]({link})")
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")