# Regulatory Topic Extraction and Markdown Enrichment

**Objective.** Extract the issue structure of proposed rules, use it to guide topic discovery in public comments, and maintain the results as readable, linked Markdown. Generate a reverse topic index for browsing and later Neo4j import.

## Markdown Data Model

| Artifact | Purpose |
|---|---|
| **`topics.md`** | Authoritative topic catalog: stable anchors, descriptions, explicit parent links, origin, and supporting evidence |
| **`initial-regulatory-issues.md`** | Initial Regulatory Issues: agency proposals and feedback requests linked to topics and anchored passages in proposed rules |
| **Enriched comment documents** | Original anchored elements with visible `🏷️ Topics:` lines linking to the catalog |
| **`topic-mapping.md`** | Generated reverse index: one section per topic, listing tagged comments and links to their specific elements |

Use explicit HTML anchors as stable identifiers for topics, issues, and document elements. Define hierarchy through parent links rather than heading depth alone. Adopt consistent field labels and link conventions so Markdown can be parsed and validated as structured data.

## Phase 1 — Extract Regulatory Building Blocks

Process proposed rules by section with LangExtract, preserving document identifiers, headings, and existing element anchors. Extract topics, proposed actions, requirements, affected parties, conditions, stated rationales, and requests for feedback.

Retain verbatim evidence and distinguish it from normalized labels or questions. Do not invent specific questions from general invitations to comment. Convert extraction spans into source-element links, retaining finer span information when useful.

LangExtract uses an LLM, such as Gemini. The subsequent CorEx analysis requires no pretrained language model.

## Phase 2 — Assemble the Initial Regulatory Issues and Topic Catalog

Use a second LangExtract pass to propose topic relationships, consolidate repeated references, and connect feedback requests to proposals. Assign stable IDs in application code and review inferred relationships.

Write the reviewed results to `topics.md` and `initial-regulatory-issues.md`. Support variable-depth topics, cross-topic proposal links, and requests concerning multiple proposals. Record whether hierarchy relationships are explicit in the source or inferred during analysis.

Keep proposals and feedback requests as linked records rather than mandatory levels of the topic hierarchy. Preserve distinctions such as exemptions, extensions, and exceptions.

## Comment Analysis and Enrichment

Build a sparse binary term matrix from anchored comment paragraphs or list items. Identify duplicate submissions while retaining their counts separately. Exclude generated annotations from analysis inputs.

Use agency-derived phrases present in the comment vocabulary to anchor selected CorEx topics. Leave additional components unanchored to discover commenter terminology and emergent concerns. Review informative terms and supporting passages before adding catalog topics or accepting mappings.

Annotate accepted assignments beneath their source elements using the Unicode **🏷️ Label** symbol:

```markdown
<a id="comment-0042-p007"></a>

Our software vendor cannot deliver the required changes before the
proposed implementation deadline.

🏷️ **Topics:** [Implementation timing](topics.md#topic-implementation-timing)
· [Vendor readiness](topics.md#topic-vendor-readiness)
```

Keep topic assignment separate from support/opposition and from answering a specific agency question. Preserve assignment method, analysis run, and review status through defined Markdown fields where required.

## Reverse Index and Neo4j Import

Generate `topic-mapping.md` from the catalog and enriched comments. Under each topic, group references by comment and list every tagged element. Include brief excerpts for readable browsing; links remain the authoritative references.

```markdown
<a id="mapping-vendor-readiness"></a>
## [Vendor readiness](topics.md#topic-vendor-readiness)

### [Comment 0042](comments/comment-0042.md)

- [Paragraph 7](comments/comment-0042.md#comment-0042-p007):
  “Our software vendor cannot deliver the required changes…”
```

Resolve relative links according to each file’s location. Store direct assignments; generate ancestor rollups separately and label them as inherited. Treat the reverse index as a reproducible view, regenerated after annotation changes.

Parse `topics.md`, `initial-regulatory-issues.md`, and `topic-mapping.md` to import topic hierarchy, regulatory relationships, documents, elements, and topic assignments into Neo4j. JSON is an optional generated transport format; Markdown remains the maintained source.

## Validation

Validate unique IDs, resolving links, acyclic parent relationships, and agreement between annotations and the reverse index. Evaluate extraction accuracy and CorEx relevance on reviewed samples. Detect source edits that invalidate evidence references, and preserve the distinction between explicit agency structure and inferred analytical organization.
