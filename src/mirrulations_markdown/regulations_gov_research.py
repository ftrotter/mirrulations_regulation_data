"""Resumable Regulations.gov metadata research and evidence collection."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.regulations.gov/v4"
RESEARCH_VERSION = 1


@dataclass(frozen=True)
class ArtifactCategory:
    key: str
    label: str
    search_term: str
    document_types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    title_terms: tuple[str, ...] = ()


CATEGORIES = (
    ArtifactCategory("rfi", "Request for information", "Request for Information",
                     title_terms=("request for information",)),
    ArtifactCategory("anprm", "Advance notice of proposed rulemaking",
                     "Advance Notice of Proposed Rulemaking", subtypes=("Advance Notice of Proposed Rulemaking (ANPRM)",),
                     title_terms=("advance notice of proposed rulemaking", "advanced notice of proposed rulemaking")),
    ArtifactCategory("nprm", "Notice of proposed rulemaking", "Proposed Rule",
                     document_types=("Proposed Rule",), title_terms=("proposed rule",)),
    ArtifactCategory("supplemental_nprm", "Supplemental proposed rule", "Supplemental Notice of Proposed Rulemaking",
                     title_terms=("supplemental notice of proposed rulemaking", "supplemental proposed rule")),
    ArtifactCategory("comment_period", "Comment-period extension or reopening", "Reopening Comment Period",
                     title_terms=("reopen", "extension of comment period", "extend the comment period")),
    ArtifactCategory("public_meeting", "Public meeting, hearing, or listening session", "Notice of Public Meeting",
                     subtypes=("Meeting", "Public Meetings"), title_terms=("public meeting", "public hearing", "listening session")),
    ArtifactCategory("negotiated_rulemaking", "Negotiated rulemaking", "Negotiated Rulemaking",
                     title_terms=("negotiated rulemaking", "regulatory negotiation")),
    ArtifactCategory("direct_final_rule", "Direct final rule", "Direct Final Rule",
                     title_terms=("direct final rule",)),
    ArtifactCategory("direct_final_withdrawal", "Withdrawal of direct final rule", "Withdrawal Direct Final Rule",
                     title_terms=("withdrawal", "direct final rule")),
    ArtifactCategory("interim_final_rule", "Interim final rule", "Interim Final Rule",
                     document_types=("Rule",), title_terms=("interim final rule",)),
    ArtifactCategory("final_rule", "Final rule", "Final Rule", document_types=("Rule",),
                     title_terms=("final rule",)),
    ArtifactCategory("correction", "Correction", "Correction",
                     title_terms=("correction", "correcting amendment")),
    ArtifactCategory("effective_date_delay", "Effective-date delay", "Delay of Effective Date",
                     title_terms=("delay of effective date", "effective date delay", "delaying the effective date")),
    ArtifactCategory("compliance_date_extension", "Compliance-date extension", "Compliance Date Extension",
                     title_terms=("compliance date extension", "extension of compliance date")),
    ArtifactCategory("amendment", "Amendment or revision", "Amendment",
                     title_terms=("amendment", "revision")),
    ArtifactCategory("withdrawal", "Withdrawal", "Withdrawal",
                     title_terms=("withdrawal", "withdrawn")),
    ArtifactCategory("rescission", "Rescission or repeal", "Rescission",
                     title_terms=("rescission", "rescind", "repeal")),
    ArtifactCategory("petition", "Petition for rulemaking or reconsideration", "Petition for Rulemaking",
                     title_terms=("petition for rulemaking", "petition for reconsideration")),
    ArtifactCategory("supporting_material", "Supporting and related material", "Supporting Related Material",
                     document_types=("Supporting & Related Material",)),
    ArtifactCategory("regulatory_impact_analysis", "Regulatory impact analysis", "Regulatory Impact Analysis",
                     title_terms=("regulatory impact analysis", "regulatory impact assessment")),
    ArtifactCategory("regulatory_flexibility", "Regulatory flexibility analysis", "Regulatory Flexibility Analysis",
                     title_terms=("regulatory flexibility analysis",)),
    ArtifactCategory("information_collection", "Information collection or PRA material", "Information Collection Request",
                     title_terms=("information collection request", "paperwork reduction act")),
    ArtifactCategory("environmental_analysis", "Environmental analysis", "Environmental Assessment",
                     title_terms=("environmental assessment", "environmental impact statement")),
    ArtifactCategory("response_to_comments", "Response to comments", "Response to Comments",
                     title_terms=("response to comments", "responses to comments")),
    ArtifactCategory("omb_interagency", "OMB or interagency-review material", "OMB Review",
                     title_terms=("omb review", "interagency review", "executive order 12866 review")),
    ArtifactCategory("sorn_initial", "Initial system of records notice", "System of Records Notice",
                     subtypes=("System of Records",), title_terms=("system of records",)),
    ArtifactCategory("sorn_modified", "Modified system of records notice", "Modified System of Records",
                     subtypes=("System of Records",), title_terms=("modified system of records",)),
    ArtifactCategory("sorn_rescinded", "Rescinded system of records notice", "Rescindment System of Records",
                     title_terms=("rescindment", "rescission", "rescind")),
)


class RegulationsGovClient:
    """Small standard-library client with durable GET response caching."""

    def __init__(self, *, api_key, cache_root, requests_per_second=2.0, retry_count=5):
        if not api_key:
            raise ValueError("regulations_gov_research.py Error: REGULATIONS_GOV_API_KEY is not set")
        if requests_per_second <= 0:
            raise ValueError("regulations_gov_research.py Error: requests_per_second must be positive")
        self.api_key = api_key
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.minimum_interval = 1.0 / requests_per_second
        self.retry_count = retry_count
        self.last_request_time = 0.0

    def get(self, *, resource_path, parameters=None):
        parameters = parameters or {}
        query = urlencode(sorted(parameters.items()))
        request_key = resource_path.strip("/").replace("/", "__")
        if query:
            import hashlib
            request_key += "__" + hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        cache_path = self.cache_root / f"{request_key}.json"
        if cache_path.is_file():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        url = f"{API_ROOT}/{resource_path.lstrip('/')}" + (f"?{query}" if query else "")
        for attempt in range(self.retry_count + 1):
            wait = self.minimum_interval - (time.monotonic() - self.last_request_time)
            if wait > 0:
                time.sleep(wait)
            try:
                with urlopen(Request(url, headers={"X-Api-Key": self.api_key}), timeout=60) as response:
                    self.last_request_time = time.monotonic()
                    payload = json.load(response)
                cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                return payload
            except HTTPError as error:
                self.last_request_time = time.monotonic()
                if error.code not in (429, 500, 502, 503, 504) or attempt == self.retry_count:
                    raise
                time.sleep(min(60.0, 2.0 ** attempt))
        raise RuntimeError("regulations_gov_research.py Error: unreachable retry state")


def _matches(*, category, document):
    attributes = document.get("attributes", {})
    title = (attributes.get("title") or "").casefold()
    document_type = attributes.get("documentType")
    subtype = attributes.get("subtype")
    type_match = not category.document_types or document_type in category.document_types
    subtype_match = not category.subtypes or subtype in category.subtypes
    title_match = not category.title_terms or any(
        term.casefold() in title for term in category.title_terms
    )
    if category.key == "sorn_initial":
        title_match = "system of records" in title and not any(term in title for term in ("modified", "rescind"))
    elif category.key == "direct_final_withdrawal":
        title_match = "direct final rule" in title and "withdraw" in title
    return type_match and subtype_match and title_match


class RegulationsGovResearch:
    @staticmethod
    def _candidate_search(*, client, category, search_size, minimum_matches,
                          maximum_search_pages=10):
        candidates = []
        for page_number in range(1, maximum_search_pages + 1):
            parameters = {
                "filter[searchTerm]": category.search_term,
                "page[number]": page_number,
                "page[size]": search_size,
            }
            if len(category.document_types) == 1:
                parameters["filter[documentType]"] = category.document_types[0]
            if len(category.subtypes) == 1:
                parameters["filter[subtype]"] = category.subtypes[0]
            search = client.get(resource_path="documents", parameters=parameters)
            candidates.extend(search.get("data", []))
            matching_count = sum(
                _matches(category=category, document=candidate)
                for candidate in candidates
            )
            if matching_count >= minimum_matches or search.get("meta", {}).get("lastPage"):
                break
        return candidates

    @staticmethod
    def collect(*, output_root, api_key=None, sample_size=5, search_size=100,
                requests_per_second=2.0, categories=CATEGORIES):
        output_root = Path(output_root)
        client = RegulationsGovClient(
            api_key=api_key or os.getenv("REGULATIONS_GOV_API_KEY"),
            cache_root=output_root / "raw_api_cache",
            requests_per_second=requests_per_second,
        )
        evidence = []
        for category in categories:
            candidates = RegulationsGovResearch._candidate_search(
                client=client, category=category, search_size=search_size,
                minimum_matches=sample_size,
            )
            accepted = []
            for candidate in candidates:
                if len(accepted) >= sample_size:
                    break
                if not _matches(category=category, document=candidate):
                    continue
                detail = client.get(resource_path=f"documents/{candidate['id']}")
                document = detail["data"]
                attributes = document.get("attributes", {})
                docket_id = attributes.get("docketId")
                docket = client.get(resource_path=f"dockets/{docket_id}") if docket_id else None
                comment_on_id = attributes.get("objectId")
                comment_search = client.get(resource_path="comments", parameters={
                    "filter[commentOnId]": comment_on_id, "page[size]": 5,
                    "sort": "postedDate",
                }) if comment_on_id else {"data": [], "meta": {"totalElements": 0}}
                comments = []
                for comment_candidate in comment_search.get("data", []):
                    comments.append(client.get(
                        resource_path=f"comments/{comment_candidate['id']}"
                    )["data"])
                accepted.append({
                    "document": document,
                    "docket": docket["data"] if docket else None,
                    "comments": comments,
                    "comment_total": comment_search.get("meta", {}).get("totalElements"),
                    "comment_search_object_id": comment_on_id,
                })
            evidence.append({
                "category_key": category.key, "category_label": category.label,
                "search_term": category.search_term, "requested_sample_size": sample_size,
                "accepted_sample_size": len(accepted), "examples": accepted,
            })
        manifest = {
            "research_version": RESEARCH_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "api_root": API_ROOT, "evidence": evidence,
        }
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "evidence_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        RegulationsGovResearch.write_summary(output_root=output_root, manifest=manifest)
        return manifest

    @staticmethod
    def write_summary(*, output_root, manifest):
        summary = {
            "research_version": manifest["research_version"],
            "generated_at": manifest["generated_at"],
            "api_root": manifest["api_root"],
            "categories": [],
        }
        document_fields = (
            "agencyId", "docketId", "documentType", "subtype", "title", "frDocNum",
            "postedDate", "commentStartDate", "commentEndDate", "effectiveDate",
            "openForComment", "withinCommentPeriod", "withdrawn", "objectId",
        )
        for category in manifest["evidence"]:
            examples = []
            for example in category["examples"]:
                document = example["document"]
                attributes = document.get("attributes", {})
                docket = example.get("docket") or {}
                examples.append({
                    "document_id": document["id"],
                    "document": {
                        field: attributes.get(field) for field in document_fields
                    },
                    "docket_id": docket.get("id"),
                    "docket_type": docket.get("attributes", {}).get("docketType"),
                    "rin": docket.get("attributes", {}).get("rin"),
                    "comment_search_object_id": example.get("comment_search_object_id"),
                    "comment_total": example.get("comment_total"),
                    "sample_comment_ids": [comment["id"] for comment in example["comments"]],
                })
            summary["categories"].append({
                "category_key": category["category_key"],
                "category_label": category["category_label"],
                "accepted_sample_size": category["accepted_sample_size"],
                "examples": examples,
            })
        output_path = Path(output_root) / "evidence_summary.json"
        output_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary