"""Citation candidates, optional adapters, reconciliation, and resolution."""

import hashlib
import importlib
import importlib.metadata
import logging
import re
from dataclasses import asdict, is_dataclass


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
    """Report Python adapter availability and explicitly deferred packages."""
    adapters = (("eyecite", "eyecite"),)
    statuses = []
    for adapter_name, module_name in adapters:
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
    statuses.extend(
        [
            {
                "adapter_name": "lexnlp",
                "status": "deferred-incompatible",
                "detail": "LexNLP 2.3.0 dependency chain is incompatible with Python 3.14",
            },
            {
                "adapter_name": "citeurl",
                "status": "deferred-evaluation",
                "detail": "Evaluate after the eyecite adapter is complete",
            },
        ]
    )
    return statuses


def _serializable_value(*, value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _serializable_value(value=item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable_value(value=item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _eyecite_normalized_target(*, citation, citation_class, corrected_citation):
    groups = citation.groups
    reporter = re.sub(r"[^A-Za-z]", "", str(groups.get("reporter", ""))).lower()
    title = groups.get("title") or groups.get("volume")
    section = groups.get("section") or groups.get("page")
    if reporter in {"usc", "cfr"} and title and section:
        return f"{reporter}:{title}:{section}"
    return (
        f"eyecite:{citation_class.lower()}:"
        f"{hashlib.sha256(corrected_citation.encode('utf-8')).hexdigest()}"
    )


def extract_eyecite_citations(*, text, document_version, block_id):
    """Extract citations with eyecite or return an independent failure record."""
    try:
        from eyecite import get_citations
        eyecite_version = importlib.metadata.version("eyecite")
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        return [], {
            "adapter_name": "eyecite",
            "status": "unavailable",
            "detail": f"{type(error).__name__}: {error}",
        }
    warning_messages = []

    class _WarningCapture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warning_messages.append(self.format(record))

    eyecite_logger = logging.getLogger("eyecite")
    warning_capture = _WarningCapture()
    previous_level = eyecite_logger.level
    eyecite_logger.addHandler(warning_capture)
    eyecite_logger.setLevel(logging.WARNING)
    try:
        eyecite_citations = get_citations(text)
    except Exception as error:  # Library exceptions are isolated per adapter.
        return [], {
            "adapter_name": "eyecite",
            "status": "failed",
            "detail": f"{type(error).__name__}: {error}",
        }
    finally:
        eyecite_logger.removeHandler(warning_capture)
        eyecite_logger.setLevel(previous_level)
    candidates = []
    for citation in eyecite_citations:
        start, end = citation.span_with_pincite()
        citation_class = type(citation).__name__
        normalized_value = citation.corrected_citation()
        normalized_target = _eyecite_normalized_target(
            citation=citation,
            citation_class=citation_class,
            corrected_citation=normalized_value,
        )
        candidates.append(
            {
                "schema_version": 1,
                "document_version": document_version,
                "block_id": block_id,
                "start": start,
                "end": end,
                "matched_text": text[start:end],
                "citation_family": (
                    "case" if "CaseCitation" in citation_class else "other-authority"
                ),
                "normalized_target": normalized_target,
                "structured_components": {
                    "citation_class": citation_class,
                    "corrected_citation": normalized_value,
                    "groups": _serializable_value(value=citation.groups),
                    "metadata": _serializable_value(value=citation.metadata),
                },
                "adapter_name": "eyecite",
                "adapter_version": eyecite_version,
                "warnings": [],
            }
        )
    return candidates, {
        "adapter_name": "eyecite",
        "adapter_version": eyecite_version,
        "status": "success",
        "finding_count": len(candidates),
        "warnings": warning_messages,
    }


def reconcile_candidates(*, candidates):
    """Merge identical findings while retaining adapters and flagging overlaps."""
    merged_by_occurrence = {}
    for candidate in candidates:
        key = (
            candidate["block_id"], candidate["start"], candidate["end"],
            candidate["normalized_target"],
        )
        if key not in merged_by_occurrence:
            merged = dict(candidate)
            merged["supporting_adapters"] = [candidate["adapter_name"]]
            merged_by_occurrence[key] = merged
        elif candidate["adapter_name"] not in merged_by_occurrence[key]["supporting_adapters"]:
            merged_by_occurrence[key]["supporting_adapters"].append(candidate["adapter_name"])
    reconciled = sorted(
        merged_by_occurrence.values(),
        key=lambda item: (item["block_id"], item["start"], item["end"]),
    )
    for index, candidate in enumerate(reconciled):
        overlaps = [
            other
            for other in reconciled[index + 1 :]
            if other["block_id"] == candidate["block_id"]
            and other["start"] < candidate["end"]
            and candidate["start"] < other["end"]
        ]
        if overlaps:
            candidate["warnings"] = sorted(set(candidate["warnings"] + ["overlap_competing_finding"]))
            for other in overlaps:
                other["warnings"] = sorted(set(other["warnings"] + ["overlap_competing_finding"]))
    return reconciled


def resolve_candidate(*, candidate):
    target_parts = candidate["normalized_target"].split(":")
    family, title, section = target_parts[:3]
    if family == "usc":
        url = f"https://www.law.cornell.edu/uscode/text/{title}/{section}"
    elif family == "cfr":
        url = f"https://www.law.cornell.edu/cfr/text/{title}/{section}"
    else:
        annotation_id = _candidate_id(
            document_version=candidate["document_version"],
            block_id=candidate["block_id"], start=candidate["start"],
            end=candidate["end"], normalized_target=candidate["normalized_target"],
        )
        return {
            **candidate,
            "annotation_id": annotation_id,
            "resolution_status": "unresolved",
        }
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
        if "overlap_competing_finding" in citation.get("warnings", []):
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