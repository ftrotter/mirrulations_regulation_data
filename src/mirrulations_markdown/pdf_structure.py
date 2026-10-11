"""Extract page and physical-line evidence from original PDFs with pypdf."""

import importlib.metadata
import logging
def _layout_lines(*, layout_text):
    return [
        {
            "text": line.strip(),
            "indent": len(line) - len(line.lstrip()),
            "is_blank": not line.strip(),
        }
        for line in layout_text.splitlines()
    ]


def _paragraphs_from_lines(*, lines):
    """Group layout-mode lines using blank rows and indentation evidence."""
    paragraphs = []
    current_lines = []
    for line in lines:
        if line["is_blank"]:
            if current_lines:
                paragraphs.append(current_lines)
                current_lines = []
            continue
        starts_new = bool(current_lines and line["indent"] > 2)
        if starts_new:
            paragraphs.append(current_lines)
            current_lines = []
        current_lines.append(line)
    if current_lines:
        paragraphs.append(current_lines)
    return [
        {
            "text": " ".join(line["text"] for line in paragraph),
            "line_count": len(paragraph),
            "indent": min(line["indent"] for line in paragraph),
        }
        for paragraph in paragraphs
    ]


def extract_pdf_structure(*, pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ValueError(
            "pdf_structure.py Error: pypdf is not installed; install requirements.txt"
        ) from error

    warning_messages = []

    class _WarningCapture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warning_messages.append(self.format(record))

    pypdf_logger = logging.getLogger("pypdf")
    warning_capture = _WarningCapture()
    previous_level = pypdf_logger.level
    pypdf_logger.addHandler(warning_capture)
    pypdf_logger.setLevel(logging.WARNING)
    try:
        reader = PdfReader(pdf_path)
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            layout_text = page.extract_text(extraction_mode="layout")
            lines = _layout_lines(layout_text=layout_text)
            pages.append(
                {
                    "page_number": page_number,
                    "lines": lines,
                    "paragraphs": _paragraphs_from_lines(lines=lines),
                }
            )
    finally:
        pypdf_logger.removeHandler(warning_capture)
        pypdf_logger.setLevel(previous_level)
    return {
        "parser": "pypdf",
        "parser_version": importlib.metadata.version("pypdf"),
        "page_count": len(pages),
        "warnings": warning_messages,
        "pages": pages,
    }