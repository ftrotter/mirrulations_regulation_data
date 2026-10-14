# MVP Graph Data Representation

## Purpose

This document defines the minimum graph representation needed for the first
topic-mining implementation. The MVP must:

1. extract regulatory issues and topics from proposed rules;
2. assign reviewed topics to comment blocks;
3. preserve evidence and processing provenance; and
4. generate a reproducible Neo4j projection.

Features not required for those tasks are deferred.

## Source of Truth

Neo4j is not the source of truth. It must be possible to delete and rebuild the
graph from files.

The authoritative MVP files are:

| File | Authority |
|---|---|
| Existing document and block sidecars | Document versions, block IDs, text, order, and source locations |
| Citation sidecars | Citation spans, normalized targets, URLs, and resolution status |
| Structure-discovery sidecars | Summaries and unresolved backward-reference descriptions |
| Exact-reference sidecars | Resolved block links, relationship classes, confidence, and rationale |
| `topics.md` | Accepted topics and parent relationships |
| `initial-regulatory-issues.md` | Accepted issues, proposals, requirements, and feedback requests |
| Topic-assignment sidecars | Topic assignments, evidence, provenance, and review status |
| Run manifests | Model, configuration, input, and execution provenance |

Enriched comment Markdown and `topic-mapping.md` are generated views. They are
useful to people but must not be imported as independent facts.

## Stable IDs

IDs must not depend on labels or filenames. Renaming a topic must not change its
ID.

New topic and issue IDs use a type prefix and an application-generated ULID:

```text
topic-01JAB7Q4H1G25Z4NR2ME19JQYT
issue-01JAB7SZTQDY8P9FVM5W5T46Y6
proposal-01JAB80CNFBCGW7F3QX48AV7H5
requirement-01JAB82TYDRX6ZK0XJ8P0GNDC4
feedback-request-01JAB8589BEFXYDVP48WMDCERW
run-01JAB900000000000000000000
```

Existing docket, document, document-version, and block IDs must be reused.
A block is globally identified by:

```text
document_version_id + block_id
```

The HTML anchor for a topic or issue record must equal its stable ID.

## MVP Nodes

The graph contains these node types:

| Node | Meaning |
|---|---|
| `Docket` | Regulatory docket |
| `Document` | Agency document, comment body, or attachment |
| `DocumentVersion` | Immutable version of a document |
| `Block` | Anchored paragraph, list, section, or other semantic block |
| `Authority` | Normalized legal or external citation target |
| `CitationOccurrence` | One citation span in one block |
| `BackwardReference` | Unresolved description of earlier material to find |
| `ExactReference` | Resolved link from a source block to target blocks |
| `Topic` | Reviewed subject concept |
| `RegulatoryIssue` | Group of related agency actions and questions |
| `Proposal` | Action contemplated by the agency |
| `Requirement` | Proposed obligation, prohibition, or deadline |
| `FeedbackRequest` | Explicit question or general invitation to comment |
| `PipelineRun` | One extraction or topic-analysis run |

Comments and agency documents use the same `Document`, `DocumentVersion`, and
`Block` structure. Their document metadata identifies their type.

## MVP Relationships

```text
Docket -HAS_DOCUMENT-> Document
Document -HAS_VERSION-> DocumentVersion
DocumentVersion -HAS_BLOCK-> Block

RegulatoryIssue -HAS_PROPOSAL-> Proposal
RegulatoryIssue -HAS_REQUIREMENT-> Requirement
RegulatoryIssue -HAS_FEEDBACK_REQUEST-> FeedbackRequest

RegulatoryIssue -ABOUT_TOPIC-> Topic
Proposal -ABOUT_TOPIC-> Topic
Requirement -ABOUT_TOPIC-> Topic
FeedbackRequest -ABOUT_TOPIC-> Topic

Topic -CHILD_OF-> Topic
Block -ASSIGNED_TOPIC-> Topic
Block -RESPONDS_TO-> Block

Block -HAS_CITATION-> CitationOccurrence
CitationOccurrence -CITES-> Authority
Block -HAS_BACKWARD_REFERENCE-> BackwardReference
BackwardReference -TARGETS_DOCUMENT-> Document
Block -HAS_EXACT_REFERENCE-> ExactReference
ExactReference -PRIMARY_TARGET-> Block
ExactReference -SUPPORTING_TARGET-> Block
```

`RESPONDS_TO` is optional in the MVP and may only be created when a resolved
reference links a comment block to an agency-document block. Docket membership
alone is not evidence of a response.

Existing citation relationships remain unchanged and may be imported beside
these relationships.

## Existing Links

Topic enrichment must preserve all links and link metadata produced by earlier
stages. It must not replace existing links with topic relationships or infer
their meaning from rendered Markdown URLs.

### Citations

Each citation occurrence preserves:

- its document version and block ID;
- start and end offsets and matched text;
- citation family and normalized target;
- resolved URL, title, and resolution status when available; and
- adapter and run provenance.

Multiple occurrences may point to the same `Authority`. A citation occurrence
remains distinct because its source span and provenance matter.

### Backward references

A Stage 3 backward reference is an unresolved search instruction:

```json
{
  "source_block_id": "paragraph-0007",
  "target_key": "document:CMS-2026-1255-0001",
  "search_description": "the proposed seven-day deadline"
}
```

It links the source block to a known target document, but not to an exact target
block. It must remain available even after exact-link processing.

### Exact references

A Stage 4 exact reference records one source block, its target document, and
zero or more target blocks. Each target has role `primary` or `supporting`.
Reference status is `linked`, `no-match`, or `ambiguous`.

The relationship class is one of:

```text
explicit_open_question
implicit_assumption_challenge
other_substantive_relationship
```

Exact references also preserve confidence, rationale, provider/model metadata,
source and target context hashes, and the producing run. No-match, ambiguous,
rejected, and failed records remain in sidecars for audit, but only accepted
`linked` records produce graph edges.

Topic similarity alone must never create an exact reference or `RESPONDS_TO`
edge. Topic assignment, citation, backward reference, and exact reference are
separate facts even when they connect the same blocks.

## Topics

Topics form a directed acyclic graph. A topic may have more than one parent.
Only direct parent relationships are stored; ancestor relationships are
generated when needed.

Each topic must contain:

- `topic_id`;
- `label`;
- `description`;
- `origin`: `agency-derived`, `comment-derived`, or `human-authored`;
- `review_status`; and
- zero or more parent topic IDs.

For the MVP, renaming a topic changes its label but keeps its ID. Topic merges,
splits, aliases, and deprecation workflows are deferred. If those situations
arise during the MVP, they require manual data correction and a recorded note.

### `topics.md` example

```markdown
<a id="topic-01JAB7Q4H1G25Z4NR2ME19JQYT"></a>
## Vendor readiness

- **Topic ID:** `topic-01JAB7Q4H1G25Z4NR2ME19JQYT`
- **Description:** Vendor ability to implement required changes by a deadline.
- **Origin:** `comment-derived`
- **Review status:** `accepted`
- **Parent topics:**
  - [Implementation timing](#topic-01JAB6XRVH4BHN0K6PBGJHP2VZ)
```

## Regulatory Issues

Regulatory issues organize the agency material that will seed topic discovery.
Proposals, requirements, and feedback requests are records linked to an issue;
they are not required levels of the topic hierarchy.

Every issue, proposal, requirement, and feedback request must contain:

- its stable ID;
- a short label or summary;
- `review_status`;
- one or more topic IDs; and
- one or more evidence references.

A feedback request also contains:

```text
question_type: explicit | general_invitation
```

A general invitation to comment must not be rewritten as a specific question.

### `initial-regulatory-issues.md` example

```markdown
<a id="issue-01JAB7SZTQDY8P9FVM5W5T46Y6"></a>
## Electronic prior authorization for drugs

- **Issue ID:** `issue-01JAB7SZTQDY8P9FVM5W5T46Y6`
- **Review status:** `accepted`
- **Topics:**
  - [Electronic prior authorization](topics.md#topic-01JAB920000000000000000000)
- **Evidence:**
  - [Proposed rule, paragraph 46](proposed-rule.md#paragraph-0046)

### Proposals

<a id="proposal-01JAB80CNFBCGW7F3QX48AV7H5"></a>
#### Require electronic prior authorization support for drugs

- **Proposal ID:** `proposal-01JAB80CNFBCGW7F3QX48AV7H5`
- **Review status:** `accepted`
- **Topics:**
  - [Electronic prior authorization](topics.md#topic-01JAB920000000000000000000)
- **Evidence:**
  - [Paragraph 46](proposed-rule.md#paragraph-0046)
```

## Evidence

Each extracted regulatory record must have at least one evidence reference.
Evidence uses the existing document and block identity instead of copying a new
document identity scheme.

```json
{
  "document_version_id": "fd1abfef...",
  "block_id": "paragraph-0046",
  "start": 120,
  "end": 684,
  "matched_text": "We propose to require..."
}
```

Offsets are Unicode code-point offsets into block `plain_text`. `start` is
inclusive and `end` is exclusive. The matched text must equal the indexed span.

If the source document changes, it creates a new document version. Evidence
against the old version remains historical and must not be silently moved.

## Topic Assignments

The authoritative topic assignment is a sidecar record:

```json
{
  "schema_version": 1,
  "assignment_id": "topic-assignment-<sha256>",
  "document_version_id": "abc123...",
  "block_id": "paragraph-0007",
  "topic_id": "topic-01JAB7Q4H1G25Z4NR2ME19JQYT",
  "assignment_method": "corex",
  "analysis_run_id": "run-01JAB900000000000000000000",
  "score": 0.82,
  "review_status": "accepted"
}
```

`assignment_method` is `agency-anchor`, `corex`, `llm`, or `human`. Scores are
method-specific and must not be compared across methods without calibration.

Only accepted assignments appear in enriched comment Markdown:

```markdown
<a id="paragraph-0007"></a>

Our software vendor cannot deliver the required changes before the proposed
implementation deadline.

🏷️ **Topics:** [Vendor readiness](../../topics.md#topic-01JAB7Q4H1G25Z4NR2ME19JQYT)
```

Only direct assignments are stored. Assignments to parent topics are generated
by traversing accepted `CHILD_OF` relationships and must be labeled as
inherited in queries and reports.

## Topic Model

The MVP topic model uses CorEx to propose topics and block assignments. CorEx
output is candidate data; it becomes graph data only after review.

### Analysis units

The analysis unit is an anchored comment paragraph or substantive list block.
Agency documents are used to create topic anchors, not as comment observations.
Each row in the model matrix must retain its document version and block ID so a
result can always be linked back to source text.

Exclude from model input:

- generated headings, summaries, topic labels, and other annotations;
- citation link markup while retaining its visible source wording;
- empty or boilerplate-only blocks; and
- blocks excluded by the configured eligibility rules.

Comment bodies and attachments remain separate documents. Exact duplicate text
may be represented once in model fitting, but the run must record every member
and its count. Near-duplicates are not collapsed in the MVP.

### Vocabulary and matrix

Build a sparse binary term matrix. A value indicates whether a term occurs in a
block, not how many times it occurs. Preprocessing must be deterministic and
recorded in the run manifest, including:

- lowercase and Unicode normalization settings;
- token and phrase construction;
- stopword source;
- minimum and maximum document frequency;
- excluded boilerplate; and
- vocabulary hash.

Agency-derived anchor phrases may be used only when they occur in the comment
vocabulary. Preserve the source regulatory issue and evidence for each anchor.
Some model components must remain unanchored so commenter terminology and
emergent concerns can be discovered.

### Model configuration

The run manifest records at least:

```json
{
  "model_type": "corex",
  "model_version": "<installed-version>",
  "topic_count": 20,
  "random_seed": 1729,
  "anchor_strength": 3,
  "vocabulary_sha256": "...",
  "matrix_sha256": "...",
  "anchors": {
    "topic-01JAB920000000000000000000": [
      "electronic prior authorization"
    ]
  }
}
```

Topic count, anchor strength, and frequency thresholds are configuration, not
fixed data-model constants. Identical input, configuration, package version,
and random seed must reproduce the same candidate output.

### Candidate output

For each model component, retain:

- component number;
- anchored topic ID, when applicable;
- total correlation or model weight supplied by the library;
- ranked informative terms and their weights;
- ranked supporting blocks and their scores; and
- run ID.

For each proposed block assignment, retain block identity, component number,
candidate topic ID when known, score, and run ID. Do not create stable topic IDs
for every component automatically. Reviewers may map a component to an existing
topic, create a new topic, or reject it as incoherent.

### Review and publication

Reviewers must inspect informative terms and representative source blocks, not
just a generated label. An accepted component-to-topic mapping and accepted
block assignment produce the `ASSIGNED_TOPIC` relationship described above.

Topic assignment means that a block discusses a topic. It does not mean the
commenter supports or opposes a proposal, and it does not mean the block answers
a feedback request. Those meanings require separate future annotations or an
existing exact-reference relationship.

At least one reviewed sample must be retained for each published model run so
topic coherence and assignment relevance can be evaluated.

## Review Status

The MVP uses three states:

```text
proposed
accepted
rejected
```

Model output begins as `proposed`. Only `accepted` records are published in
maintained Markdown, enriched comments, the reverse index, or Neo4j. A rerun
must not overwrite an accepted or rejected human decision.

Detailed review-event history and reviewer roles are deferred. The MVP must at
least preserve the current status, reviewer name, review timestamp, and a short
rationale in the authoritative sidecar.

## Pipeline Runs

Each extraction or topic-analysis run must record:

- `run_id` and run type;
- start and completion timestamps;
- completion status;
- input manifest hash;
- code commit;
- model provider and model name, when applicable;
- prompt or configuration version; and
- random seed, when applicable;
- source stage and eligibility rules;
- preprocessing and vocabulary hashes for topic-model runs; and
- package versions that affect results.

Run completion status is `complete`, `partial`, or `failed`. Partial results
must not be presented as a complete run.

## Reverse Index

`topic-mapping.md` is generated from accepted direct assignments. It contains
one section per topic and links to each assigned comment block.

```markdown
## [Vendor readiness](topics.md#topic-01JAB7Q4H1G25Z4NR2ME19JQYT)

### [Comment CMS-2026-1255-0042](comments/CMS-2026-1255-0042.md)

- [Paragraph 7](comments/CMS-2026-1255-0042.md#paragraph-0007):
  “Our software vendor cannot deliver the required changes…”
```

The reverse index must be regenerated after assignment changes. It is not an
import source.

## Neo4j Projection

Neo4j uses the node and relationship names defined above. Every node must have
a uniqueness constraint on its stable ID. A block uses the combined key:

```text
document_version_id:block_id
```

The importer must:

1. validate files before import;
2. merge nodes by stable ID;
3. merge relationships by stable endpoint IDs and relationship type;
4. import only accepted semantic records;
5. preserve citation occurrences, unresolved backward references, and accepted
   exact references from earlier stages; and
6. produce no duplicates when run twice with identical inputs.

Display labels and Markdown paths must never be used as merge keys.

### Local implementation note

The MVP is expected to run Neo4j locally in a Docker container. Connection
settings, credentials, ports, and the browser base URL must be configurable;
they must not be embedded in graph records or committed secrets. Container data
should use a persistent local volume so restarting the container does not
require an import, while the files remain authoritative and must still support
a complete rebuild.

Neo4j results must link back to the existing comment browser detail pages. The
browser currently defaults to `http://127.0.0.1:8765` and supports:

```text
/comments/{comment_id}/
/comments/{comment_id}/representations/{representation_id}/
/comments/{comment_id}/representations/{representation_id}/stage/{stage_number}/
```

Comment `Document`, `DocumentVersion`, and `Block` records must therefore retain
the existing `comment_id` and representation ID. A block link should use the
most specific available detail page and append its existing block anchor when
the rendered stage supports anchors. Submission-level results may use the
comment detail page.

The application layer constructs these URLs from the configured browser base
URL and stable graph properties. Neo4j should store identifiers and optional
relative paths, not a machine-specific absolute URL. Links must target the same
source-demarcated representation and stage from which the graph record was
imported.

## MVP Validation

Before publishing or importing a run, validate that:

1. stable IDs are unique;
2. every Markdown link and anchor resolves;
3. every evidence block exists in the stated document version;
4. every evidence span is in bounds and matches `matched_text`;
5. accepted topic parent relationships contain no cycles;
6. every accepted assignment points to an existing block and accepted topic;
7. enriched comment tags exactly match accepted direct assignments;
8. `topic-mapping.md` exactly matches accepted direct assignments; and
9. every imported existing link resolves to its authoritative sidecar record;
10. exact references preserve status, target role, and relationship class;
11. topic-model candidate blocks resolve to the exact matrix rows and source
    blocks used by the recorded run; and
12. rerunning generation or import with the same inputs creates no duplicates.

## Deferred Beyond the MVP

The following are intentionally deferred:

- topic merge, split, alias, and deprecation workflows;
- append-only review-event nodes;
- near-duplicate submission detection and duplicate-group graph nodes;
- normalized affected-party, condition, and rationale nodes;
- relationship-level evidence nodes;
- graph transport formats beyond the sidecars needed for import;
- automatic migration of evidence to new document versions; and
- graph optimization beyond required uniqueness constraints.

These features may be added without changing the MVP rule that files are
authoritative and Neo4j is a reproducible projection.

## MVP Acceptance Criteria

The MVP representation is ready for implementation when one fixture can show:

1. a proposed-rule block with one regulatory issue and topic;
2. a comment block with one accepted direct topic assignment;
3. one inherited parent-topic result;
4. evidence resolving to exact source text;
5. one citation occurrence, one backward reference, and one accepted exact
   reference preserved from existing sidecars;
6. one reproducible topic-model component with terms, supporting blocks, and a
   reviewed assignment;
7. matching enriched Markdown and `topic-mapping.md`; and
8. a Neo4j graph that can be deleted and rebuilt without changing IDs or
   creating duplicates.
