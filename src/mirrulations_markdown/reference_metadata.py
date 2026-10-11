"""Cached authority titles and persistent human-editable reference names."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request

from .friendly_metadata import parse_markdown_table_row


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.parts = []

    def handle_starttag(self, tag, _attributes):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data)


def normalized_reference_text(*, normalized_target):
    parts = normalized_target.split(":")
    if len(parts) >= 3 and parts[0] in {"usc", "cfr"}:
        family = "U.S.C." if parts[0] == "usc" else "CFR"
        subsection = "".join(f"({part})" for part in parts[3:])
        return f"{parts[1]} {family} § {parts[2]}{subsection}"
    return normalized_target


def fetch_official_title(*, url, opener=None):
    request = urllib.request.Request(
        url, headers={"User-Agent": "mirrulations-regulation-data/1.0"}
    )
    selected_opener = opener or urllib.request.urlopen
    with selected_opener(request, timeout=15) as response:
        html_text = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        status = getattr(response, "status", 200)
    parser = _TitleParser()
    parser.feed(html_text)
    title = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
    if "law.cornell.edu" in final_url:
        title = title.split(" | ", 1)[0].strip()
    if not title:
        raise ValueError("reference_metadata.py Error: destination page has no title")
    return {"official_reference_name": title, "final_url": final_url, "http_status": status}


def title_matches_reference(*, title, normalized_target):
    parts = normalized_target.split(":")
    if len(parts) < 3 or parts[0] not in {"usc", "cfr"}:
        return True
    normalized_title = re.sub(r"[^a-z0-9]", "", title.lower())
    family_token = "usc" if parts[0] == "usc" else "cfr"
    expected_prefix = re.sub(
        r"[^a-z0-9]", "", f"{parts[1]}{family_token}{parts[2]}".lower()
    )
    return expected_prefix in normalized_title


def resolve_reference_names(
    *, citations, cache_path, refresh=False, opener=None, maximum_fetches=10
):
    cache = {}
    if cache_path.is_file():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        for cache_record in cache.values():
            if (
                "law.cornell.edu" in (cache_record.get("final_url") or "")
                and " | " in cache_record.get("official_reference_name", "")
            ):
                cache_record["official_reference_name"] = cache_record[
                    "official_reference_name"
                ].split(" | ", 1)[0].strip()
    fetch_count = 0
    for citation in citations:
        target = citation["normalized_target"]
        fallback = citation.get("reference_text") or normalized_reference_text(
            normalized_target=target
        )
        if (
            target in cache
            and cache[target].get("status") != "fetch-deferred-budget"
            and not refresh
        ):
            continue
        url = citation.get("destination_url")
        if not url:
            cache[target] = {
                "official_reference_name": fallback, "status": "unresolved",
                "requested_url": None, "error": "No resolved destination URL",
            }
            continue
        if fetch_count >= maximum_fetches:
            continue
        try:
            fetch_count += 1
            fetched = fetch_official_title(url=url, opener=opener)
            if title_matches_reference(
                title=fetched["official_reference_name"],
                normalized_target=target,
            ):
                cache[target] = {
                    **fetched, "status": "fetched", "requested_url": url,
                    "identity_verified": True,
                }
            else:
                cache[target] = {
                    "official_reference_name": fallback,
                    "status": "identity-mismatch", "requested_url": url,
                    "final_url": fetched["final_url"],
                    "http_status": fetched["http_status"],
                    "identity_verified": False,
                    "error": "Fetched title did not match normalized authority",
                }
        except Exception as error:
            cache[target] = {
                "official_reference_name": fallback, "status": "fetch-failed",
                "requested_url": url,
                "error": f"{type(error).__name__}: {error}",
            }
    for citation in citations:
        target = citation["normalized_target"]
        if target not in cache:
            cache[target] = {
                "official_reference_name": normalized_reference_text(
                    normalized_target=target
                ) if not citation.get("reference_text") else citation["reference_text"],
                "status": "fetch-deferred-budget",
                "requested_url": citation.get("destination_url"),
            }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cache, fetch_count


def _read_reference_edits(*, table_path):
    edits = {}
    if not table_path.is_file():
        return edits
    for line in table_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line or "official_reference_name" in line:
            continue
        cells = parse_markdown_table_row(line=line)
        if len(cells) == 4:
            edits[(cells[2], cells[3])] = cells[1]
    return edits


def write_reference_friendly_names(*, table_path, references):
    edits = _read_reference_edits(table_path=table_path)
    lines = [
        "# Reference Friendly Names", "",
        "| official_reference_name | friendly_reference_name | reference_text | reference_url |",
        "|---|---|---|---|",
    ]
    selected_names = {}
    for reference in sorted(references, key=lambda item: item["normalized_target"]):
        key = (reference["reference_text"], reference.get("reference_url") or "")
        official = reference["official_reference_name"]
        edited_friendly = edits.get(key, "")
        cells = (official, edited_friendly, key[0], key[1])
        lines.append("| " + " | ".join(
            str(value).replace("|", "\\|").replace("\n", " ") for value in cells
        ) + " |")
        selected_names[reference["normalized_target"]] = edited_friendly or official
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return selected_names