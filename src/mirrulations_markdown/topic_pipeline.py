"""End-to-end regulatory extraction, CorEx topic fitting, and graph export."""

from collections import Counter
from datetime import datetime, timezone
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

from corextopic import corextopic
from scipy.sparse import csr_matrix

from .graph_browser_links import comment_browser_url
from .graph_io import write_graph_bundle
from .graph_models import GraphBundle, GraphNode, GraphRelationship


ANALYSIS_BLOCK_TYPES = {"paragraph", "list"}
STAGE_4 = "stage004_backward_reference_links"
STAGE_5 = "stage005_topic_enrichment"
TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9-]{2,}", re.IGNORECASE)
STOP_WORDS = {
    "about", "after", "also", "and", "are", "because", "been", "being",
    "between", "but", "can", "could", "does", "each", "for", "from", "had",
    "has", "have", "into", "its", "may", "more", "must", "not", "our",
    "should", "such", "than", "that", "the", "their", "these", "they", "this",
    "through", "under", "use", "using", "was", "were", "which", "will", "with",
    "would", "your", "cms", "comment", "comments", "proposed", "rule",
}
REGULATORY_ACTION_PATTERN = re.compile(
    r"\b(?:we propose|we are proposing|we seek comment|we solicit comment|"
    r"we request comment|would require|propose to require)\b",
    re.IGNORECASE,
)


def _canonical_json_hash(*, value):
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _stable_ulid(*, prefix, identity):
    digest = hashlib.sha256(identity.encode("utf-8")).digest()[:16]
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
    encoded = encoded.translate(str.maketrans("ILOU", "1110"))[:26]
    return f"{prefix}-{encoded}"


def _tokens(*, text):
    return {
        token.lower() for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS and not token.isdigit()
    }


def load_corpus(*, markdown_db_path, browser_base_url):
    """Load document/block authority once and retain browser identities."""
    documents = []
    comments = []
    regulatory_documents = []
    block_by_key = {}
    for block_path in sorted((Path(markdown_db_path) / "metadata" / "blocks").glob("*.json")):
        record = json.loads(block_path.read_text(encoding="utf-8"))
        metadata = record.get("document_metadata") or {}
        role = metadata.get("logical_document_role")
        source_sha256 = record["asset"]["source_sha256"]
        document_id = metadata.get("document_id") or Path(
            record["asset"]["source_object_key"]
        ).stem
        representation_id = block_path.stem
        document_version_id = f"{representation_id}:{source_sha256}"
        document = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "source_sha256": source_sha256,
            "representation_id": representation_id,
            "role": role,
            "docket_id": metadata.get("docket_id"),
            "title": metadata.get("title") or metadata.get("generated_friendly_name"),
            "asset": record["asset"],
            "blocks": record.get("blocks", []),
        }
        for block in document["blocks"]:
            block_key = f"{document_version_id}:{block['block_id']}"
            browser_url = None
            if role in {"form_comment", "comment_attachment"}:
                browser_url = comment_browser_url(
                    browser_base_url=browser_base_url,
                    comment_id=document_id,
                    representation_id=representation_id,
                    stage_number=5,
                    block_id=block["block_id"],
                )
            block_by_key[block_key] = {
                **block,
                "block_key": block_key,
                "document_id": document_id,
                "document_version_id": source_sha256,
                "representation_id": representation_id,
                "role": role,
                "browser_url": browser_url,
            }
        documents.append(document)
        if role in {"form_comment", "comment_attachment"}:
            comments.append(document)
        elif role == "regulatory_document":
            regulatory_documents.append(document)
    if not regulatory_documents:
        raise ValueError("topic_pipeline.py Error: no regulatory document found")
    return {
        "documents": documents,
        "comments": comments,
        "regulatory_documents": regulatory_documents,
        "block_by_key": block_by_key,
    }


def _rule_based_regulatory_extraction(*, regulatory_document):
    """Create transparent development anchors from source section headings."""
    candidates = []
    for block in regulatory_document["blocks"]:
        if block["block_type"] != "section":
            continue
        label = re.sub(r"^[A-Z0-9IVX.()]+\s*", "", block["plain_text"]).strip()
        if len(label) < 8:
            continue
        topic_id = _stable_ulid(prefix="topic", identity=f"agency-topic|{label.lower()}")
        issue_id = _stable_ulid(prefix="issue", identity=f"agency-issue|{label.lower()}")
        candidates.append({
            "issue_id": issue_id,
            "label": label[:160],
            "topic_id": topic_id,
            "topic_label": label[:100],
            "block_id": block["block_id"],
            "evidence_text": block["plain_text"],
            "extraction_method": "rule-based-section-heading",
            "review_status": "accepted",
        })
    return _deduplicate_issues(issues=candidates)


def _deduplicate_issues(*, issues):
    unique_issues = {}
    for issue in issues:
        unique_issues.setdefault(issue["issue_id"], issue)
    return list(unique_issues.values())


def _langextract_examples():
    from langextract.core import data
    example_text = (
        "We propose to require impacted payers to implement electronic prior "
        "authorization by January 1, 2028. We seek comment on that deadline."
    )
    return [data.ExampleData(text=example_text, extractions=[
        data.Extraction(
            extraction_class="proposal",
            extraction_text=(
                "require impacted payers to implement electronic prior "
                "authorization by January 1, 2028"
            ),
            attributes={"topic": "electronic prior authorization"},
        ),
        data.Extraction(
            extraction_class="feedback_request",
            extraction_text="We seek comment on that deadline",
            attributes={"topic": "implementation deadline"},
        ),
    ])]


def extract_regulatory_issues(
    *, regulatory_document, mode, model_id=None, api_key=None, extractor=None,
    checkpoint_path=None,
):
    if mode == "rule-based":
        return _rule_based_regulatory_extraction(
            regulatory_document=regulatory_document
        )
    if mode != "langextract":
        raise ValueError(
            "topic_pipeline.py Error: regulatory extraction mode must be "
            "langextract or rule-based"
        )
    if not api_key and extractor is None:
        raise ValueError(
            "topic_pipeline.py Error: LangExtract requires LANGEXTRACT_API_KEY "
            "or GEMINI_API_KEY"
        )
    selected_extractor = extractor
    if selected_extractor is None:
        import langextract as lx
        selected_extractor = lx.extract
    candidates = []
    checkpoint_records = {}
    selected_checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
    if selected_checkpoint_path and selected_checkpoint_path.is_file():
        checkpoint_records = json.loads(
            selected_checkpoint_path.read_text(encoding="utf-8")
        ).get("blocks", {})
    for block in regulatory_document["blocks"]:
        if block["block_type"] not in {"section", "paragraph", "list"}:
            continue
        text = block["plain_text"].strip()
        if len(text) < 80 or not REGULATORY_ACTION_PATTERN.search(text):
            continue
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached_record = checkpoint_records.get(block["block_id"])
        if cached_record and cached_record.get("source_sha256") == source_hash:
            candidates.extend(cached_record.get("issues", []))
            continue
        result = selected_extractor(
            text_or_documents=text,
            prompt_description=(
                "Extract agency proposals, proposed requirements, and requests "
                "for feedback. Use exact source wording. Give each extraction a "
                "short topic attribute. Do not invent a question from a general "
                "invitation to comment."
            ),
            examples=_langextract_examples(),
            model_id=model_id or "gemini-3.8-flash",
            api_key=api_key,
            max_char_buffer=4000,
            extraction_passes=1,
            show_progress=False,
        )
        for extraction in result.extractions or []:
            topic_label = str((extraction.attributes or {}).get("topic") or "").strip()
            if not topic_label:
                continue
            topic_id = _stable_ulid(
                prefix="topic", identity=f"agency-topic|{topic_label.lower()}"
            )
            issue_identity = (
                f"{extraction.extraction_class}|{extraction.extraction_text.lower()}"
            )
            entity_prefix = {
                "proposal": "proposal",
                "requirement": "requirement",
                "feedback_request": "feedback-request",
            }.get(extraction.extraction_class, "issue")
            char_interval = getattr(extraction, "char_interval", None)
            candidates.append({
                "issue_id": _stable_ulid(prefix="issue", identity=issue_identity),
                "entity_id": _stable_ulid(
                    prefix=entity_prefix, identity=issue_identity
                ),
                "label": extraction.extraction_text[:160],
                "topic_id": topic_id,
                "topic_label": topic_label[:100],
                "block_id": block["block_id"],
                "evidence_text": extraction.extraction_text,
                "extraction_class": extraction.extraction_class,
                "extraction_method": "langextract",
                "review_status": "proposed",
                "evidence_start": getattr(char_interval, "start_pos", None),
                "evidence_end": getattr(char_interval, "end_pos", None),
            })
        if selected_checkpoint_path:
            checkpoint_records[block["block_id"]] = {
                "source_sha256": source_hash,
                "issues": [
                    issue for issue in candidates
                    if issue["block_id"] == block["block_id"]
                ],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(
                path=selected_checkpoint_path,
                value={"schema_version": 1, "blocks": checkpoint_records},
            )
    return _deduplicate_issues(issues=candidates)


def fit_corex_topics(
    *, comments, agency_issues, topic_count, random_seed, minimum_document_frequency,
    maximum_document_fraction, anchor_strength, assignment_threshold,
    maximum_topics_per_block=3,
):
    rows_by_text_hash = {}
    duplicate_members = {}
    document_frequency = Counter()
    for document in comments:
        for block in document["blocks"]:
            text = block.get("plain_text", "").strip()
            if block.get("block_type") not in ANALYSIS_BLOCK_TYPES or len(text) < 40:
                continue
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            block_record = {
                "document_id": document["document_id"],
                "document_version_id": document["document_version_id"],
                "representation_id": document["representation_id"],
                "block_id": block["block_id"],
                "block_key": f"{document['document_version_id']}:{block['block_id']}",
                "text": text,
            }
            duplicate_members.setdefault(text_hash, []).append(block_record)
            if text_hash not in rows_by_text_hash:
                terms = _tokens(text=text)
                rows_by_text_hash[text_hash] = {**block_record, "terms": terms}
                document_frequency.update(terms)
    rows = [rows_by_text_hash[key] for key in sorted(rows_by_text_hash)]
    maximum_document_frequency = max(1, int(len(rows) * maximum_document_fraction))
    vocabulary = sorted(
        term for term, frequency in document_frequency.items()
        if minimum_document_frequency <= frequency <= maximum_document_frequency
    )
    if not vocabulary:
        raise ValueError("topic_pipeline.py Error: topic-model vocabulary is empty")
    vocabulary_index = {term: index for index, term in enumerate(vocabulary)}
    matrix_rows = []
    matrix_columns = []
    for row_index, row in enumerate(rows):
        for term in row["terms"]:
            if term in vocabulary_index:
                matrix_rows.append(row_index)
                matrix_columns.append(vocabulary_index[term])
    matrix = csr_matrix(
        ([1] * len(matrix_rows), (matrix_rows, matrix_columns)),
        shape=(len(rows), len(vocabulary)), dtype="int8",
    )
    topic_frequency = Counter(issue["topic_id"] for issue in agency_issues)
    first_issue_by_topic = {}
    for issue in agency_issues:
        first_issue_by_topic.setdefault(issue["topic_id"], issue)
    anchor_candidates = []
    for topic_id, issue in first_issue_by_topic.items():
        anchor_terms = [
            term for term in _tokens(text=issue["topic_label"])
            if term in vocabulary_index
        ]
        if anchor_terms:
            # CorEx 1.1's nested sparse anchor indexing is incompatible with
            # current SciPy. One scalar term per component is fully supported.
            anchor_candidates.append({
                "topic_id": topic_id,
                "anchor": sorted(anchor_terms)[0],
                "frequency": topic_frequency[topic_id],
            })
    anchor_candidates.sort(
        key=lambda item: (-item["frequency"], item["topic_id"])
    )
    selected_topic_count = min(topic_count, len(vocabulary))
    selected_anchors = anchor_candidates[:selected_topic_count]
    anchor_topic_ids = [item["topic_id"] for item in selected_anchors]
    anchors = [item["anchor"] for item in selected_anchors]
    padded_anchors = anchors
    model = corextopic.Corex(
        n_hidden=selected_topic_count, seed=random_seed, max_iter=200,
        count="binarize",
    )
    model.fit(
        matrix, words=vocabulary, anchors=padded_anchors,
        anchor_strength=anchor_strength,
    )
    topics = []
    assignment_candidates = []
    agency_topic_by_id = first_issue_by_topic
    for component_index in range(selected_topic_count):
        informative_terms = [
            {"term": term, "weight": round(float(weight), 8), "sign": float(sign)}
            for term, weight, sign in model.get_topics(topic=component_index, n_words=12)
            if sign > 0
        ]
        if component_index < len(anchor_topic_ids):
            topic_id = anchor_topic_ids[component_index]
            label = agency_topic_by_id[topic_id]["topic_label"]
            origin = "agency-derived"
        else:
            label_terms = [item["term"] for item in informative_terms[:4]]
            label = " / ".join(label_terms) or f"Component {component_index + 1}"
            topic_id = _stable_ulid(
                prefix="topic",
                identity=f"corex|{random_seed}|{'|'.join(label_terms)}",
            )
            origin = "comment-derived"
        probabilities = model.p_y_given_x[:, component_index]
        supporting_indexes = sorted(
            range(len(rows)), key=lambda index: (-probabilities[index], index)
        )[:10]
        topics.append({
            "topic_id": topic_id,
            "label": label[:100],
            "description": (
                "CorEx component characterized by: "
                + ", ".join(item["term"] for item in informative_terms[:8])
            ),
            "origin": origin,
            "review_status": "accepted",
            "component": component_index,
            "total_correlation": round(float(model.tcs[component_index]), 8),
            "informative_terms": informative_terms,
            "supporting_blocks": [
                {
                    "block_key": rows[index]["block_key"],
                    "score": round(float(probabilities[index]), 8),
                    "excerpt": rows[index]["text"][:240],
                }
                for index in supporting_indexes
            ],
        })
        for row_index, probability in enumerate(probabilities):
            if float(probability) < assignment_threshold:
                continue
            for member in duplicate_members[
                hashlib.sha256(rows[row_index]["text"].encode("utf-8")).hexdigest()
            ]:
                assignment_identity = (
                    f"{member['document_version_id']}|{member['block_id']}|"
                    f"{topic_id}|{random_seed}"
                )
                assignment_candidates.append({
                    "assignment_id": "topic-assignment-" + hashlib.sha256(
                        assignment_identity.encode("utf-8")
                    ).hexdigest(),
                    "document_id": member["document_id"],
                    "document_version_id": member["document_version_id"],
                    "representation_id": member["representation_id"],
                    "block_id": member["block_id"],
                    "block_key": member["block_key"],
                    "topic_id": topic_id,
                    "score": round(float(probability), 8),
                    "review_status": "accepted",
                    "reviewer": "mvp-auto-review",
                    "review_rationale": (
                        f"CorEx posterior met configured threshold "
                        f"{assignment_threshold}."
                    ),
                })
    assignments_by_block = {}
    for assignment in assignment_candidates:
        assignments_by_block.setdefault(assignment["block_key"], []).append(assignment)
    assignments = []
    for block_key in sorted(assignments_by_block):
        assignments.extend(sorted(
            assignments_by_block[block_key],
            key=lambda item: (-item["score"], item["topic_id"]),
        )[:maximum_topics_per_block])
    return {
        "topics": topics,
        "assignments": assignments,
        "row_count": len(rows),
        "source_block_count": sum(len(value) for value in duplicate_members.values()),
        "exact_duplicate_count": sum(
            max(0, len(value) - 1) for value in duplicate_members.values()
        ),
        "vocabulary": vocabulary,
        "vocabulary_sha256": _canonical_json_hash(value=vocabulary),
        "matrix_sha256": hashlib.sha256(
            matrix.data.tobytes() + matrix.indices.tobytes() + matrix.indptr.tobytes()
        ).hexdigest(),
        "total_correlation": round(float(model.tc), 8),
    }


def _write_json(*, path, value):
    selected_path = Path(path)
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = selected_path.with_suffix(selected_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(selected_path)


def render_topic_markdown(*, topics, output_path):
    lines = ["# Topic Catalog", ""]
    for topic in sorted(topics, key=lambda item: item["topic_id"]):
        lines.extend([
            f'<a id="{topic["topic_id"]}"></a>',
            f'## {topic["label"]}', "",
            f'- **Topic ID:** `{topic["topic_id"]}`',
            f'- **Description:** {topic["description"]}',
            f'- **Origin:** `{topic["origin"]}`',
            f'- **Review status:** `{topic["review_status"]}`',
            "- **Parent topics:** None", "",
        ])
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def render_issues_markdown(*, issues, regulatory_document, output_path):
    lines = ["# Initial Regulatory Issues", ""]
    source_path = regulatory_document["asset"]["markdown_path"]
    for issue in sorted(issues, key=lambda item: item["issue_id"]):
        lines.extend([
            f'<a id="{issue["issue_id"]}"></a>', f'## {issue["label"]}', "",
            f'- **Issue ID:** `{issue["issue_id"]}`',
            f'- **Review status:** `{issue["review_status"]}`',
            "- **Topics:**",
            f'  - [{issue["topic_label"]}](topics.md#{issue["topic_id"]})',
            "- **Evidence:**",
            f'  - [{issue["block_id"]}]({source_path}#{issue["block_id"]})',
            f'- **Extraction method:** `{issue["extraction_method"]}`', "",
        ])
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def render_topic_mapping(*, topics, assignments, corpus, output_path):
    topic_by_id = {topic["topic_id"]: topic for topic in topics}
    block_by_key = corpus["block_by_key"]
    assignments_by_topic = {}
    for assignment in assignments:
        assignments_by_topic.setdefault(assignment["topic_id"], []).append(assignment)
    lines = ["# Topic Mapping", ""]
    for topic_id in sorted(assignments_by_topic):
        topic = topic_by_id[topic_id]
        lines.extend([
            f'<a id="mapping-{topic_id}"></a>',
            f'## [{topic["label"]}](topics.md#{topic_id})', "",
        ])
        for assignment in sorted(
            assignments_by_topic[topic_id],
            key=lambda item: (item["document_id"], item["block_id"]),
        ):
            block = block_by_key[assignment["block_key"]]
            lines.extend([
                f'- [{assignment["document_id"]} — {assignment["block_id"]}]'
                f'({block["browser_url"]}): {block["plain_text"][:180]}',
            ])
        lines.append("")
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def render_topic_enriched_stage(
    *, markdown_db_path, corpus, topics, assignments, topic_catalog_path,
):
    """Render accepted topic links into a new immutable corpus projection."""
    topic_by_id = {topic["topic_id"]: topic for topic in topics}
    assignments_by_representation = {}
    for assignment in assignments:
        assignments_by_representation.setdefault(
            assignment["representation_id"], {}
        ).setdefault(assignment["block_id"], []).append(assignment)
    stage_4_root = Path(markdown_db_path) / STAGE_4
    stage_5_root = Path(markdown_db_path) / STAGE_5
    for document in corpus["comments"]:
        source_path = stage_4_root / document["asset"]["markdown_path"]
        if not source_path.is_file():
            continue
        target_path = stage_5_root / document["asset"]["markdown_path"]
        rendered = source_path.read_text(encoding="utf-8")
        block_assignments = assignments_by_representation.get(
            document["representation_id"], {}
        )
        anchor_pattern = re.compile(
            r'<a id="(?P<block_id>(?:section|paragraph|list|quotation|label|table)-\d{4})"></a>'
        )
        anchor_matches = list(anchor_pattern.finditer(rendered))
        for match_index in reversed(range(len(anchor_matches))):
            match = anchor_matches[match_index]
            accepted_assignments = block_assignments.get(match.group("block_id"), [])
            if not accepted_assignments:
                continue
            next_start = (
                anchor_matches[match_index + 1].start()
                if match_index + 1 < len(anchor_matches) else len(rendered)
            )
            relative_catalog_path = Path(__import__("os").path.relpath(
                topic_catalog_path, start=target_path.parent
            )).as_posix()
            links = []
            for assignment in sorted(
                accepted_assignments, key=lambda item: (-item["score"], item["topic_id"])
            ):
                topic = topic_by_id[assignment["topic_id"]]
                links.append(
                    f'[{topic["label"]}]({relative_catalog_path}#{topic["topic_id"]})'
                )
            annotation = "\n\n🏷️ **Topics:** " + " · ".join(links) + "\n"
            rendered = rendered[:next_start].rstrip() + annotation + "\n" + rendered[next_start:]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = target_path.with_suffix(target_path.suffix + ".tmp")
        temporary_path.write_text(rendered, encoding="utf-8")
        temporary_path.replace(target_path)


def build_graph_bundle(*, corpus, topics, assignments, issues, run_id, markdown_db_path):
    nodes = []
    relationships = []
    docket_ids = sorted({doc["docket_id"] for doc in corpus["documents"] if doc["docket_id"]})
    for docket_id in docket_ids:
        nodes.append(GraphNode(label="Docket", stable_id=docket_id))
    document_identities = set()
    for document in corpus["documents"]:
        document_key = f"{document['document_id']}:{document['representation_id']}"
        document_identities.add(document_key)
        nodes.extend([
            GraphNode(
                label="Document", stable_id=document_key,
                properties={
                    "document_id": document["document_id"],
                    "representation_id": document["representation_id"],
                    "role": document["role"], "title": document["title"],
                },
            ),
            GraphNode(
                label="DocumentVersion", stable_id=document["document_version_id"],
                properties={"source_object_key": document["asset"]["source_object_key"]},
            ),
        ])
        if document["docket_id"]:
            relationships.append(GraphRelationship(
                relationship_type="HAS_DOCUMENT", source_label="Docket",
                source_id=document["docket_id"], target_label="Document",
                target_id=document_key,
            ))
        relationships.append(GraphRelationship(
            relationship_type="HAS_VERSION", source_label="Document",
            source_id=document_key, target_label="DocumentVersion",
            target_id=document["document_version_id"],
        ))
        for block in document["blocks"]:
            block_key = f"{document['document_version_id']}:{block['block_id']}"
            authoritative_block = corpus["block_by_key"][block_key]
            nodes.append(GraphNode(
                label="Block", stable_id=block_key,
                properties={
                    "block_id": block["block_id"], "block_type": block["block_type"],
                    "order": block["order"], "plain_text": block["plain_text"],
                    "document_id": document["document_id"],
                    "representation_id": document["representation_id"],
                    "browser_url": authoritative_block["browser_url"],
                },
            ))
            relationships.append(GraphRelationship(
                relationship_type="HAS_BLOCK", source_label="DocumentVersion",
                source_id=document["document_version_id"], target_label="Block",
                target_id=block_key,
            ))
    for topic in topics:
        nodes.append(GraphNode(
            label="Topic", stable_id=topic["topic_id"],
            properties={key: topic[key] for key in (
                "label", "description", "origin", "review_status", "component",
                "total_correlation",
            )},
        ))
    for assignment in assignments:
        relationships.append(GraphRelationship(
            relationship_type="ASSIGNED_TOPIC", source_label="Block",
            source_id=assignment["block_key"], target_label="Topic",
            target_id=assignment["topic_id"],
            properties={
                "assignment_id": assignment["assignment_id"],
                "score": assignment["score"], "review_status": "accepted",
            },
        ))
    regulatory_document = corpus["regulatory_documents"][0]
    for issue in issues:
        entity_label = {
            "proposal": "Proposal",
            "requirement": "Requirement",
            "feedback_request": "FeedbackRequest",
        }.get(issue.get("extraction_class"), "RegulatoryIssue")
        entity_id = issue.get("entity_id") or issue["issue_id"]
        nodes.append(GraphNode(
            label=entity_label, stable_id=entity_id,
            properties={"label": issue["label"], "method": issue["extraction_method"]},
        ))
        relationships.append(GraphRelationship(
            relationship_type="ABOUT_TOPIC", source_label=entity_label,
            source_id=entity_id, target_label="Topic",
            target_id=issue["topic_id"],
        ))
        relationships.append(GraphRelationship(
            relationship_type="SUPPORTED_BY", source_label=entity_label,
            source_id=entity_id, target_label="Block",
            target_id=f"{regulatory_document['document_version_id']}:{issue['block_id']}",
        ))
    _append_citations(
        nodes=nodes, relationships=relationships, corpus=corpus,
        markdown_db_path=markdown_db_path,
    )
    _append_exact_references(
        nodes=nodes, relationships=relationships, corpus=corpus,
        markdown_db_path=markdown_db_path,
    )
    _append_backward_references(
        nodes=nodes, relationships=relationships, corpus=corpus,
        markdown_db_path=markdown_db_path,
    )
    unique_nodes = {}
    for node in nodes:
        node_key = (node.label, node.stable_id)
        if node_key in unique_nodes and unique_nodes[node_key].properties != node.properties:
            raise ValueError(
                "topic_pipeline.py Error: conflicting graph node properties for "
                f"{node_key}"
            )
        unique_nodes.setdefault(node_key, node)
    unique_relationships = {}
    for relationship in relationships:
        relationship_key = (
            relationship.relationship_type,
            relationship.source_label,
            relationship.source_id,
            relationship.target_label,
            relationship.target_id,
        )
        if relationship_key not in unique_relationships:
            unique_relationships[relationship_key] = relationship
            continue
        existing_relationship = unique_relationships[relationship_key]
        merged_properties = {
            **existing_relationship.properties,
            **relationship.properties,
        }
        unique_relationships[relationship_key] = existing_relationship.model_copy(
            update={"properties": merged_properties}
        )
    return GraphBundle(
        generated_by_run_id=run_id,
        nodes=list(unique_nodes.values()),
        relationships=list(unique_relationships.values()),
    )


def _append_citations(*, nodes, relationships, corpus, markdown_db_path):
    block_keys_by_source = {}
    for block in corpus["block_by_key"].values():
        source_sha256 = block["document_version_id"].rsplit(":", 1)[-1]
        block_keys_by_source.setdefault(
            (source_sha256, block["block_id"]), []
        ).append(block["block_key"])
    authority_ids = set()
    occurrence_ids = set()
    citation_root = Path(markdown_db_path) / "metadata" / "annotations" / "citation_candidates"
    for citation_path in sorted(citation_root.glob("*.json")):
        record = json.loads(citation_path.read_text(encoding="utf-8"))
        for citation in record.get("candidates", []):
            block_keys = block_keys_by_source.get(
                (citation["document_version"], citation["block_id"]), []
            )
            if not block_keys:
                continue
            authority_id = citation["normalized_target"]
            if authority_id not in authority_ids:
                nodes.append(GraphNode(
                    label="Authority", stable_id=authority_id,
                    properties={"citation_family": citation["citation_family"]},
                ))
                authority_ids.add(authority_id)
            for block_key in block_keys:
                occurrence_id = "citation-" + hashlib.sha256(
                    f"{block_key}|{citation['start']}|{citation['end']}|{authority_id}".encode()
                ).hexdigest()
                if occurrence_id in occurrence_ids:
                    continue
                nodes.append(GraphNode(
                    label="CitationOccurrence", stable_id=occurrence_id,
                    properties={key: citation.get(key) for key in (
                        "start", "end", "matched_text", "adapter_name", "adapter_version",
                    )},
                ))
                occurrence_ids.add(occurrence_id)
                relationships.extend([
                    GraphRelationship(
                        relationship_type="HAS_CITATION", source_label="Block",
                        source_id=block_key, target_label="CitationOccurrence",
                        target_id=occurrence_id,
                    ),
                    GraphRelationship(
                        relationship_type="CITES", source_label="CitationOccurrence",
                        source_id=occurrence_id, target_label="Authority",
                        target_id=authority_id,
                    ),
                ])


def _append_exact_references(*, nodes, relationships, corpus, markdown_db_path):
    block_by_document_and_id = {}
    for block in corpus["block_by_key"].values():
        block_by_document_and_id[(block["document_id"], block["block_id"])] = block["block_key"]
    reference_ids = set()
    reference_root = Path(markdown_db_path) / "metadata" / "reference_links"
    for reference_path in sorted(reference_root.glob("*.json")):
        record = json.loads(reference_path.read_text(encoding="utf-8"))
        source_document = next(
            (
                document for document in corpus["documents"]
                if document["representation_id"] == reference_path.stem
            ),
            None,
        )
        if source_document is None:
            continue
        source_version = source_document["document_version_id"]
        for reference in record.get("links", []):
            source_key = f"{source_version}:{reference['source_block_id']}"
            if source_key not in corpus["block_by_key"]:
                continue
            reference_id = "exact-reference-" + reference["link_hash"]
            if reference_id not in reference_ids:
                nodes.append(GraphNode(
                    label="ExactReference", stable_id=reference_id,
                    properties={
                        "status": reference["status"],
                        "confidence": reference.get("confidence"),
                        "search_description": reference["search_description"],
                        "rationale": reference.get("rationale"),
                    },
                ))
                reference_ids.add(reference_id)
                relationships.append(GraphRelationship(
                    relationship_type="HAS_EXACT_REFERENCE", source_label="Block",
                    source_id=source_key, target_label="ExactReference",
                    target_id=reference_id,
                ))
            if reference["status"] != "linked":
                continue
            for target in reference.get("targets", []):
                target_key = block_by_document_and_id.get((
                    target["target_document_id"], target["target_block_id"]
                ))
                if not target_key:
                    continue
                relationships.append(GraphRelationship(
                    relationship_type="PRIMARY_TARGET",
                    source_label="ExactReference", source_id=reference_id,
                    target_label="Block", target_id=target_key,
                    properties={"retrieval_score": target.get("retrieval_score")},
                ))


def _append_backward_references(*, nodes, relationships, corpus, markdown_db_path):
    document_nodes_by_id = {}
    for document in corpus["documents"]:
        document_nodes_by_id.setdefault(document["document_id"], []).append(
            f"{document['document_id']}:{document['representation_id']}"
        )
    annotation_root = (
        Path(markdown_db_path) / "metadata" / "structure_discovery" / "annotations"
    )
    for annotation_path in sorted(annotation_root.glob("*.json")):
        source_document = next((
            document for document in corpus["documents"]
            if document["representation_id"] == annotation_path.stem
        ), None)
        if source_document is None:
            continue
        record = json.loads(annotation_path.read_text(encoding="utf-8"))
        for annotation in record.get("annotations", []):
            source_key = (
                f"{source_document['document_version_id']}:"
                f"{annotation['block_id']}"
            )
            for reference_index, reference in enumerate(
                annotation.get("backward_references", [])
            ):
                identity = (
                    f"{source_key}|{reference_index}|"
                    f"{reference['search_description']}"
                )
                reference_id = "backward-reference-" + hashlib.sha256(
                    identity.encode("utf-8")
                ).hexdigest()
                nodes.append(GraphNode(
                    label="BackwardReference", stable_id=reference_id,
                    properties={
                        "search_description": reference["search_description"],
                        "target_key": reference["target_key"],
                    },
                ))
                relationships.append(GraphRelationship(
                    relationship_type="HAS_BACKWARD_REFERENCE",
                    source_label="Block", source_id=source_key,
                    target_label="BackwardReference", target_id=reference_id,
                ))
                target_document_id = reference["target_key"].split(":", 1)[-1]
                for target_document_node in document_nodes_by_id.get(
                    target_document_id, []
                ):
                    relationships.append(GraphRelationship(
                        relationship_type="TARGETS_DOCUMENT",
                        source_label="BackwardReference", source_id=reference_id,
                        target_label="Document", target_id=target_document_node,
                    ))


def run_topic_pipeline(
    *, markdown_db_path, output_root, browser_base_url, extraction_mode,
    model_id=None, api_key=None, topic_count=20, random_seed=1729,
    minimum_document_frequency=10, maximum_document_fraction=0.8,
    anchor_strength=3, assignment_threshold=0.9, maximum_topics_per_block=3,
    extractor=None,
):
    started_at = datetime.now(timezone.utc)
    corpus = load_corpus(
        markdown_db_path=markdown_db_path, browser_base_url=browser_base_url
    )
    regulatory_document = corpus["regulatory_documents"][0]
    issues = extract_regulatory_issues(
        regulatory_document=regulatory_document, mode=extraction_mode,
        model_id=model_id, api_key=api_key, extractor=extractor,
        checkpoint_path=Path(output_root) / "langextract_checkpoint.json",
    )
    model_result = fit_corex_topics(
        comments=corpus["comments"], agency_issues=issues,
        topic_count=topic_count, random_seed=random_seed,
        minimum_document_frequency=minimum_document_frequency,
        maximum_document_fraction=maximum_document_fraction,
        anchor_strength=anchor_strength,
        assignment_threshold=assignment_threshold,
        maximum_topics_per_block=maximum_topics_per_block,
    )
    modeled_topic_ids = {topic["topic_id"] for topic in model_result["topics"]}
    for issue in issues:
        if issue["topic_id"] in modeled_topic_ids:
            continue
        model_result["topics"].append({
            "topic_id": issue["topic_id"],
            "label": issue["topic_label"],
            "description": (
                "Agency-derived topic retained from the regulatory issue model; "
                "its label did not produce a CorEx anchor in the comment vocabulary."
            ),
            "origin": "agency-derived",
            "review_status": issue["review_status"],
            "component": -1,
            "total_correlation": 0.0,
            "informative_terms": [],
            "supporting_blocks": [],
        })
        modeled_topic_ids.add(issue["topic_id"])
    run_identity = _canonical_json_hash(value={
        "regulatory_source": regulatory_document["document_version_id"],
        "comment_versions": sorted(doc["document_version_id"] for doc in corpus["comments"]),
        "extraction_mode": extraction_mode, "model_id": model_id,
        "topic_count": topic_count, "random_seed": random_seed,
        "minimum_document_frequency": minimum_document_frequency,
        "maximum_document_fraction": maximum_document_fraction,
        "anchor_strength": anchor_strength,
        "assignment_threshold": assignment_threshold,
        "maximum_topics_per_block": maximum_topics_per_block,
    })
    run_id = _stable_ulid(prefix="run", identity=run_identity)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_record = {
        "schema_version": 1, "run_id": run_id, "status": "complete",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "regulatory_extraction": {
            "method": extraction_mode, "model": model_id,
            "langextract_version": importlib.metadata.version("langextract"),
            "issue_count": len(issues),
        },
        "topic_model": {
            "model_type": "corex", "model_version": importlib.metadata.version("corextopic"),
            "topic_count": len(model_result["topics"]), "random_seed": random_seed,
            "anchor_strength": anchor_strength,
            "assignment_threshold": assignment_threshold,
            "maximum_topics_per_block": maximum_topics_per_block,
            "row_count": model_result["row_count"],
            "source_block_count": model_result["source_block_count"],
            "exact_duplicate_count": model_result["exact_duplicate_count"],
            "vocabulary_sha256": model_result["vocabulary_sha256"],
            "matrix_sha256": model_result["matrix_sha256"],
            "total_correlation": model_result["total_correlation"],
        },
    }
    _write_json(path=output_root / "run.json", value=run_record)
    _write_json(path=output_root / "regulatory_issues.json", value={"issues": issues})
    _write_json(path=output_root / "topics.json", value={"topics": model_result["topics"]})
    _write_json(path=output_root / "topic_assignments.json", value={
        "assignments": model_result["assignments"]
    })
    render_topic_markdown(
        topics=model_result["topics"], output_path=output_root / "topics.md"
    )
    render_issues_markdown(
        issues=issues, regulatory_document=regulatory_document,
        output_path=output_root / "initial-regulatory-issues.md",
    )
    render_topic_mapping(
        topics=model_result["topics"], assignments=model_result["assignments"],
        corpus=corpus, output_path=output_root / "topic-mapping.md",
    )
    render_topic_enriched_stage(
        markdown_db_path=markdown_db_path, corpus=corpus,
        topics=model_result["topics"], assignments=model_result["assignments"],
        topic_catalog_path=output_root / "topics.md",
    )
    graph_bundle = build_graph_bundle(
        corpus=corpus, topics=model_result["topics"],
        assignments=model_result["assignments"], issues=issues, run_id=run_id,
        markdown_db_path=markdown_db_path,
    )
    write_graph_bundle(bundle=graph_bundle, bundle_path=output_root / "graph_bundle.json")
    return {
        "run_id": run_id, "issue_count": len(issues),
        "topic_count": len(model_result["topics"]),
        "assignment_count": len(model_result["assignments"]),
        "node_count": len(graph_bundle.nodes),
        "relationship_count": len(graph_bundle.relationships),
        "output_root": str(output_root),
    }