"""Conservative conversion of published HTM, JSON, and TXT assets."""

import html
from html.parser import HTMLParser
import json
import re


BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "div", "footer", "header",
    "li", "main", "nav", "p", "section", "table", "tr",
}


class _MarkdownHTMLParser(HTMLParser):
    """Small, non-executing HTML-to-Markdown parser for source documents."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.link_stack = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attributes):
        attributes_by_name = dict(attributes)
        if tag in {"script", "style"}:
            self.ignored_depth += 1
        elif self.ignored_depth:
            return
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(f"\n\n{'#' * int(tag[1])} ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "blockquote":
            self.parts.append("\n\n> ")
        elif tag == "a":
            self.link_stack.append(attributes_by_name.get("href"))
            self.parts.append("[")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif self.ignored_depth:
            return
        elif tag == "a" and self.link_stack:
            href = self.link_stack.pop()
            self.parts.append(f"]({href})" if href else "]")
        elif tag in BLOCK_TAGS or tag.startswith("h") and tag[1:].isdigit():
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def _normalize_markdown(*, markdown_text):
    # NUL makes common text tools treat Markdown as binary. Preserve exact
    # source bytes separately through their source hash and mapping metadata.
    markdown_text = markdown_text.replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in markdown_text.splitlines()]
    normalized_lines = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        normalized_lines.append(line)
        previous_blank = is_blank
    return "\n".join(normalized_lines).strip() + "\n"


def html_to_markdown(*, html_text):
    parser = _MarkdownHTMLParser()
    parser.feed(html_text)
    parser.close()
    return _normalize_markdown(markdown_text="".join(parser.parts))


def text_to_markdown(*, text):
    paragraphs = re.split(r"\n[ \t]*\n+", text.replace("\r\n", "\n"))
    escaped_paragraphs = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if paragraph:
            escaped_paragraphs.append(re.sub(r"^(#{1,6}|[-+*]) ", r"\\\1 ", paragraph))
    return _normalize_markdown(markdown_text="\n\n".join(escaped_paragraphs))


def _find_json_content(*, json_value):
    preferred_names = ("content", "body", "comment", "text", "description")
    if isinstance(json_value, dict):
        for preferred_name in preferred_names:
            candidate = json_value.get(preferred_name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate, preferred_name
        for key, candidate in json_value.items():
            found_content = _find_json_content(json_value=candidate)
            if found_content:
                content, child_path = found_content
                return content, f"{key}.{child_path}"
    elif isinstance(json_value, list):
        for index, candidate in enumerate(json_value):
            found_content = _find_json_content(json_value=candidate)
            if found_content:
                content, child_path = found_content
                return content, f"[{index}].{child_path}"
    return None


def json_to_markdown(*, json_text):
    json_value = json.loads(json_text)
    found_content = _find_json_content(json_value=json_value)
    if not found_content:
        readable_json = json.dumps(json_value, ensure_ascii=False, indent=2, sort_keys=True)
        return f"```json\n{readable_json}\n```\n", "$"
    content, json_path = found_content
    if re.search(r"</?[a-zA-Z][^>]*>", content):
        return html_to_markdown(html_text=html.unescape(content)), json_path
    return text_to_markdown(text=content), json_path