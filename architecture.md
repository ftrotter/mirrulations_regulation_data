# Architecture

## Design principles

The system separates evidence from projections:

1. The verified Mirrulations source tree is immutable input.
2. Machine-readable JSON sidecars and manifests are authoritative ETL state.
3. Each Markdown stage is an immutable projection of the prior stage plus one
   enrichment.
4. The graph bundle is a deterministic file-backed projection.
5. Neo4j and the comment browser are disposable analysis interfaces.

Logs and PID files report operational state; they do not establish completion.

## Data flow

```text
Mirrulations source mirror
        │
        ▼
Stage 1 semantic Markdown ── metadata/blocks
        │
        ▼
Stage 2 citations ────────── metadata/annotations
        │
        ▼
Stage 3 structure ────────── metadata/structure_discovery
        │
        ▼
Stage 4 exact references ─── metadata/reference_links
        │
        ▼
LangExtract + CorEx ──────── metadata/topic_graph
        │                          │
        ▼                          ▼
Stage 5 topic Markdown       graph_bundle.json
                                   │
                                   ▼
                            local Neo4j projection
```

## Markdown database

```text
data/markdown_db/
├── stage001_initial_markdown_mirror/
├── stage002_addition_of_citations/
├── stage003_structure_discovery/
├── stage004_backward_reference_links/
├── stage005_topic_enrichment/
└── metadata/
    ├── annotations/
    ├── blocks/
    ├── manifests/
    ├── reference_links/
    ├── structure_discovery/
    └── topic_graph/
```

Stage 1 preserves source wording while assigning semantic block anchors such as
`paragraph-0046`. Stage 2 adds normalized citation links. Stage 3 adds summaries
and backward-reference descriptions. Stage 4 resolves those references to exact
regulatory blocks. Stage 5 adds links to accepted topics.

Block sidecars preserve document version, block ID, order, type, plain text,
source location, and logical role. Later annotations point back to exact
evidence without rewriting source text. See
[RichDocumentStructure.md](RichDocumentStructure.md) for the full contract.

## Topic model

LangExtract processes eligible regulatory-action passages and creates typed
agency anchors, including proposals and feedback requests. Each anchor retains
verbatim evidence and a normalized topic association.

CorEx fits topical components over eligible public-comment blocks. Accepted
assignments retain a score, analysis run, method, review status, document
version, and block ID. Exact duplicate blocks are tracked rather than silently
inflating the model.

`metadata/topic_graph/` contains:

- `run.json`: analysis provenance and configuration;
- `regulatory_issues.json`: regulatory anchors and evidence;
- `topics.json`: normalized topic records;
- `topic_assignments.json`: accepted block-level assignments;
- `langextract_checkpoint.json`: resumable extraction state;
- maintained Markdown reports; and
- `graph_bundle.json`: deterministic nodes and relationships.

## Graph schema

### Document hierarchy

```text
(Docket)-[:HAS_DOCUMENT]->(Document)
(Document)-[:HAS_VERSION]->(DocumentVersion)
(DocumentVersion)-[:HAS_BLOCK]->(Block)
```

`Document` is a logical representation, such as a form comment or attachment.
`DocumentVersion` identifies exact source bytes. `Block` is the addressable unit
of evidence and carries plain text, order, type, document ID, representation ID,
and—when it is a comment block—a local browser URL.

### Regulatory anchors and topics

```text
(Proposal)-[:ABOUT_TOPIC]->(Topic)
(Proposal)-[:SUPPORTED_BY]->(Block)
(FeedbackRequest)-[:ABOUT_TOPIC]->(Topic)
(FeedbackRequest)-[:SUPPORTED_BY]->(Block)
```

The anchor is an extracted agency statement. `SUPPORTED_BY` points to the
regulatory-action evidence block; `ABOUT_TOPIC` connects it to the normalized
topic used for comment analysis.

### Comment topics

```text
(Block)-[:ASSIGNED_TOPIC]->(Topic)
(Document)-[:DISCUSSES_TOPIC]->(Topic)
```

`ASSIGNED_TOPIC` is the detailed evidence relationship. It carries assignment
ID, score, and review status. `DISCUSSES_TOPIC` is a deterministic aggregation
for whole-comment visualization. It carries:

- `matched_block_count`: accepted blocks in that representation for the topic;
- `maximum_score`: strongest accepted block assignment.

The aggregate never replaces block evidence. It exists so Neo4j can display a
native force-directed overview without rendering tens of thousands of block
nodes or requiring APOC virtual relationships.

### Citations

```text
(Block)-[:HAS_CITATION]->(CitationOccurrence)-[:CITES]->(Authority)
```

Occurrences remain separate from normalized authorities so repeated citations
can share one legal target while preserving source location and wording.

### Backward and exact references

```text
(Block)-[:HAS_BACKWARD_REFERENCE]->(BackwardReference)
(BackwardReference)-[:TARGETS_DOCUMENT]->(Document)

(Block)-[:HAS_EXACT_REFERENCE]->(ExactReference)
(ExactReference)-[:PRIMARY_TARGET]->(Block)
```

Stage 3 records what a passage appears to refer backward to. Stage 4 records the
exact selected target and retrieval evidence. Detection and resolution remain
separate so both can be audited independently.

## Stable identities and idempotency

Graph nodes use `(label, stable_id)` identity. Stable IDs derive from source
identity, content hashes, semantic block IDs, deterministic hashes, or ULIDs;
display labels and filenames are never merge keys. A relationship is unique by
type and its two typed endpoints.

The serializer validates endpoints, rejects conflicting node properties, sorts
records, and writes atomically. The importer creates uniqueness constraints and
uses `MERGE`, so importing an unchanged bundle twice does not duplicate data.

## Interfaces

The comment browser is a local read-only HTTP projection over Markdown and block
metadata. It groups form comments and attachments into submissions, exposes all
available stages, and supports exact block anchors.

Neo4j is a local graph projection used for discovery and visualization. It is
not the source of truth and may be recreated from `graph_bundle.json`. See
[usage.md](usage.md) for the canonical queries.

## Restart behavior

- Stage 3 reuses completed segment hashes.
- Stage 4 and quality review checkpoint accepted results.
- LangExtract atomically checkpoints completed passages.
- CorEx and graph outputs regenerate from authoritative files.
- Neo4j imports are idempotent.

API-call budgets, failed records, missing block coverage, stale registries, and
incomplete checkpoints prevent silent claims of completion.
