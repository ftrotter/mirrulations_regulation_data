# Summary of the Analysis Approach

We will add functionality to this project to support structural analysis of
regulatory actions and public comments. The analysis will accommodate two
common patterns, both of which follow the typical sequence of the regulatory
process.

## Regulatory Process

The regulatory process generally follows this sequence:

1. An agency publishes a proposed rule and receives comments about it. In some
   cases, the initial regulatory action is a request for information (RFI)
   rather than a proposed rule.
2. After receiving the comments, the agency takes a subsequent regulatory
   action. This is usually a final rule, although it may be another proposed
   rule. The subsequent action refers and responds to the earlier comments.

## Analysis Modes

The project will support two modes of analysis:

1. **Regulatory action and comment analysis:** Analyze one or more regulatory
   actions together with the comments submitted in response to them.
2. **Comment-response analysis:** Analyze an initial regulatory action, the
   comments submitted in response, and a subsequent regulatory action that
   references or addresses those comments.

## Progressive Document Enrichment

Both analysis modes will use a series of progressively enriched documents.
Each stage will produce a new version while preserving the output from the
previous stage. This creates a traceable progression that shows how the source
material is structured, analyzed, and enriched with additional metadata.

The process will begin by creating:

- structured representations of regulatory documents; and
- plain-text representations of comments, whether the source comments are
  stored as JSON or text.

These representations will then be converted to Markdown. The initial Markdown
will be stored separately from each enriched version. Every enrichment stage
will write to a new location rather than overwrite an earlier version.

This approach preserves the complete analysis history and makes it possible to
inspect the metadata added during each stage.

## Markdown Database and Stage Conventions

All Markdown enrichment stages write beneath a configurable Markdown database
root. The `MARKDOWN_DB_PATH` environment variable selects that root. When it is
not set, the repository-local default is `./data/markdown_db/`.

The Markdown database and the Mirrulations source tree are separate trees.
Neither root may be equal to, contain, or be contained by the other. The source
mirror is immutable pipeline input; generated Markdown, manifests, logs,
annotations, caches, temporary files, and run records must never be written
inside it, except for the explicitly approved post-verification JSON
pretty-print normalization described by the initial-stage specification.

Acquisition must first be verified against Mirrulations. After successful
verification, downloaded JSON may be pretty-printed in place for human browsing.
The source tree is therefore byte-exact only before normalization. Preserve both
the verified remote-compatible hash and the normalized local hash, and never
describe a normalized tree as a byte-exact mirror.

Every readable enrichment is stored in an ordered, descriptively named stage
directory, for example:

```text
data/markdown_db/
  stage001_initial_markdown_mirror/
  stage002_addition_of_citations/
  stage003_future_enrichment/
  metadata/
    manifests/
    documents/
    blocks/
    annotations/
    runs/
    cache/
  logs/
```

The number identifies enrichment order, while the remainder of the directory
name describes the stage. Later development may add new `stageNNN_*`
directories without changing earlier stage names or contents.

Each enrichment stage must:

1. read source material or a prior immutable stage as explicitly specified;
2. write its readable output to a new stage directory;
3. never overwrite or mine its own previously rendered output;
4. preserve source-relative identity with a deterministic, collision-free path
   mapping;
5. record the source object key and SHA-256 hash for every derivative;
6. store authoritative machine-readable metadata in sidecars, with Markdown as
   the readable projection;
7. be deterministic and idempotent for the same source bytes, configuration,
   and tool versions; and
8. report recoverable per-asset failures while continuing independent work and
   returning a non-success status when requested work is incomplete.

Run records must preserve the effective configuration, source verification
status, dependency versions, processing counts, and detailed errors. Caches and
targeted reruns may improve efficiency, but must not change the reproducible
result. Changed source bytes create a distinct source version and invalidate
dependent output rather than silently replacing its provenance.

Actual `.env` files are local configuration and must not be overwritten by the
pipeline. Versioned example environment files document supported settings.

Global human-editable metadata belongs under the Markdown database `metadata/`
directory. Regeneration may add records and refresh generated columns, but must
not overwrite edited friendly names. Citation and document friendly names are
global across all dockets in the configured Markdown database.

## Graph Analysis

Later in the process, highly enriched Markdown representations of the comments
and regulatory actions will be loaded into a Neo4j database. Neo4j will support
efficient analysis of relationships among regulatory actions, comments,
responses, citations, and other extracted entities.

Separate Markdown documents will describe the detailed requirements and
processing steps for each stage.

## Development approach

We will focus the development one stage at a time. Do not execute against a future stages until the current one is complete.
Look ahead for context, but not for tasks.
