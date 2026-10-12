"""Extract semantic paragraph, list, heading, quotation, and table evidence from DOCX."""

import importlib.metadata


def _paragraph_type(*, paragraph):
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    paragraph_properties = paragraph._p.pPr
    has_numbering = bool(
        paragraph_properties is not None
        and paragraph_properties.numPr is not None
    )
    if style_name.startswith("heading"):
        return "section"
    if has_numbering or "list" in style_name:
        return "list-item"
    if "quote" in style_name:
        return "quotation"
    text = paragraph.text.strip()
    if text.endswith(":") and len(text) <= 80:
        return "label"
    return "paragraph"


def extract_docx_structure(*, docx_path):
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as error:
        raise ValueError(
            "docx_structure.py Error: python-docx is not installed"
        ) from error
    document = Document(docx_path)
    units = []
    for child in document.iter_inner_content():
        if isinstance(child, Paragraph):
            text = child.text.strip()
            if text:
                units.append({
                    "text": text,
                    "type_hint": _paragraph_type(paragraph=child),
                    "style_name": child.style.name if child.style else None,
                })
        elif isinstance(child, Table):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in child.rows
            ]
            if rows:
                units.append({"text": "", "type_hint": "table", "rows": rows})
    return {
        "parser": "python-docx",
        "parser_version": importlib.metadata.version("python-docx"),
        "page_count": None,
        "warnings": [],
        "units": units,
    }