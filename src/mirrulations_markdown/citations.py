"""Citation candidates, optional adapters, reconciliation, and resolution."""

import hashlib
import importlib
import importlib.metadata
import re


EXPLICIT_CITATION_PATTERN = re.compile(
    r"(?P<title>\d+)\s+(?P<family>U\.?\s*S\.?\s*C\.?|C\.?\s*F\.?\s*R\.?)"
    r"\s*(?:§{1,2}|secs?\.?|sections?)?\s*"
    r"(?P<section>\d+[A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*)"
    r"(?P<subsections>(?:\([A-Za-z0-9]+\))*)",
    re.IGNORECASE,
)


def _candidate_id(*, document_version, block_id, start, end, normalized_target):
    identity = f"{document_version}|{block_id}|{start}|{end}|{normalized_target}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def extract_explicit_citations(*, text, document_version, block_id):
    """Extract unambiguous USC/CFR references as a named built-in baseline."""
    candidates = []
    for match in EXPLICIT_CITATION_PATTERN.finditer(text):
        family_text = re.sub(r"[^A-Za-z]", "", match.group("family")).lower()
        family = "usc" if family_text == "usc" else "cfr"
        subsection_parts = re.findall(r"[A-Za-z0-9]+", match.group("subsections"))
        target_parts = [family, match.group("title"), match.group("section")]
        target_parts.extend(part.lower() for part in subsection_parts)
        normalized_target = ":".join(target_parts)
        candidates.append(
            {
                "schema_version": 1,
                "document_version": document_version,
                "block_id": block_id,
                "start": match.start(),
                "end": match.end(),
                "matched_text": match.group(0),
                "citation_family": family,
                "normalized_target": normalized_target,
                "adapter_name": "builtin_explicit_usc_cfr",
                "adapter_version": "1",
                "warnings": [],
            }
        )
    return candidates


def external_adapter_statuses():
    """Report genuine library availability without substituting another parser."""
    adapters = (
        ("eyecite", "eyecite"),
        ("lexnlp", "lexnlp"),
        ("unitedstates/citation", None),
    )
    statuses = []
    for adapter_name, module_name in adapters:
        if module_name is None:
            statuses.append(
                {
                    "adapter_name": adapter_name,
                    "status": "unavailable",
                    "detail": "Node adapter is not installed or configured",
                }
            )
            continue
        try:
            importlib.import_module(module_name)
            version = importlib.metadata.version(module_name)
        except (ImportError, importlib.metadata.PackageNotFoundError) as error:
            statuses.append(
                {
                    "adapter_name": adapter_name,
                    "status": "unavailable",
                    "detail": f"{type(error).__name__}: {error}",
                }
            )
        else:
            statuses.append(
                {"adapter_name": adapter_name, "status": "available", "version": version}
            )
    return statuses


def resolve_candidate(*, candidate):
    target_parts = candidate["normalized_target"].split(":")
    family, title, section = target_parts[:3]
    if family == "usc":
        url = f"https://www.law.cornell.edu/uscode/text/{title}/{section}"
    elif family == "cfr":
        url = f"https://www.law.cornell.edu/cfr/text/{title}/{section}"
    else:
        return {**candidate, "resolution_status": "unresolved"}
    annotation_id = _candidate_id(
        document_version=candidate["document_version"],
        block_id=candidate["block_id"],
        start=candidate["start"],
        end=candidate["end"],
        normalized_target=candidate["normalized_target"],
    )
    return {
        **candidate,
        "annotation_id": annotation_id,
        "resolution_status": "resolved",
        "destination_provider": "Cornell LII",
        "destination_url": url,
        "link_precision": "section",
        "url_verification_status": "pending",
    }


def render_citations(*, text, citations):
    rendered_text = text
    for citation in sorted(citations, key=lambda item: item["start"], reverse=True):
        if citation.get("resolution_status") != "resolved":
            continue
        start, end = citation["start"], citation["end"]
        matched_text = rendered_text[start:end]
        if matched_text != citation["matched_text"]:
            raise ValueError(
                "citations.py Error: citation span does not match block text for "
                f"{citation['annotation_id']}"
            )
        rendered_text = (
            rendered_text[:start]
            + f"[{matched_text}]({citation['destination_url']})"
            + rendered_text[end:]
        )
    return rendered_text