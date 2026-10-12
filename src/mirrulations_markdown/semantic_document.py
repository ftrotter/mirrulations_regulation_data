"""Normalize source formats into semantic blocks and clean Markdown."""

from html.parser import HTMLParser
import html
import re


SEMANTIC_TYPES = (
    "section", "paragraph", "list-item", "quotation", "label", "table"
)
HEADING_PATTERN = re.compile(
    r"^(?:[IVXLCDM]+\.|[A-Z]\.|\d+(?:\.\d+)*\.?)\s+\S+", re.IGNORECASE
)


def normalize_source_text(*, text):
    normalized_text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "")
        .replace("\u00a0", " ")
    )
    return re.sub(
        r"(?i)<\s*/?\s*br\s*/?\s*>", "<br>", normalized_text
    )


class _SemanticHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.units = []
        self.buffer = []
        self.type_hint = None
        self.table_rows = []
        self.current_row = []
        self.current_cell = []
        self.in_table = False

    def _flush(self, *, type_hint=None):
        text = re.sub(r"[ \t]+", " ", "".join(self.buffer)).strip()
        self.buffer = []
        if text:
            self.units.append({"text": text, "type_hint": type_hint or self.type_hint})
        self.type_hint = None

    def handle_starttag(self, tag, _attributes):
        tag = tag.lower()
        if tag == "br":
            self._flush()
        elif tag in {"p", "div", "section", "address"}:
            self._flush()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self.type_hint = "section"
        elif tag == "li":
            self._flush()
            self.type_hint = "list-item"
        elif tag == "blockquote":
            self._flush()
            self.type_hint = "quotation"
        elif tag == "table":
            self._flush()
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.current_row = []
        elif tag in {"td", "th"} and self.in_table:
            self.current_cell = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"p", "div", "section", "address", "li", "blockquote"} or tag.startswith("h"):
            self._flush()
        elif tag in {"td", "th"} and self.in_table:
            self.current_row.append(re.sub(r"\s+", " ", "".join(self.current_cell)).strip())
            self.current_cell = []
        elif tag == "tr" and self.in_table and self.current_row:
            self.table_rows.append(self.current_row)
        elif tag == "table":
            self.in_table = False
            if self.table_rows:
                self.units.append({"text": "", "type_hint": "table", "rows": self.table_rows})
            self.table_rows = []

    def handle_data(self, data):
        if self.in_table and self.current_cell is not None:
            self.current_cell.append(data)
        else:
            parts = re.split(r"\n[ \t]*\n+", data)
            for index, part in enumerate(parts):
                if index:
                    self._flush()
                self.buffer.append(part)

    def close(self):
        super().close()
        self._flush()


def _classify_unit(*, unit):
    text = normalize_source_text(text=html.unescape(unit.get("text", ""))).strip()
    hint = unit.get("type_hint")
    if hint == "table":
        return "table", text
    if hint in SEMANTIC_TYPES:
        return hint, text
    if text.startswith(("•", "▪", "●", "- ", "* ")):
        return "list-item", re.sub(r"^(?:[•▪●]|[-*])\s*", "", text)
    if HEADING_PATTERN.match(text) and len(text) <= 180:
        return "section", text
    if text.endswith(":") and len(text) <= 80:
        return "label", text
    return "paragraph", text


def assign_semantic_ids(*, units):
    counters = {block_type: 0 for block_type in SEMANTIC_TYPES}
    blocks = []
    parent_section_id = None
    for order, unit in enumerate(units, start=1):
        block_type, text = _classify_unit(unit=unit)
        counters[block_type] += 1
        block_id = f"{block_type}-{counters[block_type]:04d}"
        block = {
            "block_id": block_id,
            "block_type": block_type,
            "order": order,
            "plain_text": text,
            "parent_section_id": parent_section_id,
            "heading_context": [],
        }
        if block_type == "section":
            parent_section_id = block_id
            block["parent_section_id"] = None
            block["heading_level"] = 2
        if block_type == "table":
            block["rows"] = unit["rows"]
        blocks.append(block)
    return blocks


def aligned_to_semantic_blocks(*, aligned_blocks):
    units = []
    for aligned_block in aligned_blocks:
        aligned_type = aligned_block.get("block_type")
        type_hint = {
            "heading": "section",
            "paragraph": "paragraph",
            "unmatched-canonical": None,
            "list-item": "list-item",
            "quotation": "quotation",
            "label": "label",
            "table": "table",
        }.get(aligned_type)
        unit = {
            "text": aligned_block["plain_text"],
            "type_hint": (
                aligned_type if aligned_type in SEMANTIC_TYPES else type_hint
            ),
            "alignment_metadata": {
                key: value
                for key, value in aligned_block.items()
                if key not in {"block_id", "block_type", "plain_text", "order"}
            },
        }
        if aligned_type == "table" and "rows" in aligned_block:
            unit["rows"] = aligned_block["rows"]
        units.append(unit)
    blocks = assign_semantic_ids(units=units)
    for block, unit in zip(blocks, units):
        block.update(unit["alignment_metadata"])
    return blocks


def html_to_semantic_blocks(*, html_text):
    parser = _SemanticHTMLParser()
    parser.feed(normalize_source_text(text=html_text))
    parser.close()
    return assign_semantic_ids(units=parser.units)


def render_semantic_markdown(*, blocks, text_renderer=None):
    rendered = []
    for block in blocks:
        text = text_renderer(block) if text_renderer else block["plain_text"]
        rendered.append(f'<a id="{block["block_id"]}"></a>')
        rendered.append("")
        if block["block_type"] == "section":
            rendered.append(f"## {text}")
        elif block["block_type"] == "list-item":
            rendered.append(f"- {text}")
        elif block["block_type"] == "quotation":
            rendered.append(f"> {text}")
        elif block["block_type"] == "label":
            rendered.append(f"**{text}**")
        elif block["block_type"] == "table":
            rows = block.get("rows", [])
            if rows:
                width = max(len(row) for row in rows)
                padded = [row + [""] * (width - len(row)) for row in rows]
                rendered.append("| " + " | ".join(padded[0]) + " |")
                rendered.append("|" + "|".join("---" for _ in range(width)) + "|")
                rendered.extend("| " + " | ".join(row) + " |" for row in padded[1:])
        else:
            rendered.append(text)
        rendered.append("")
    return "\n".join(rendered).rstrip() + "\n"