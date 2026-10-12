# Rich Markdown Document Structure

This is the contract for the generated Markdown database.

> Machine-readable sidecars are authoritative. Markdown is their readable,
> deterministic projection.

The Mirrulations source mirror is immutable input. The Markdown database is
rebuildable output. Their roots must never overlap.

## Directory structure

```text
data/markdown_db/
├── stage001_initial_markdown_mirror/
├── stage002_addition_of_citations/
├── stage003_structure_discovery/
├── stage004_backward_reference_links/
└── metadata/
    ├── blocks/
    ├── annotations/
    │   ├── citation_candidates/
    │   └── citations/
    ├── structure_discovery/annotations/
    ├── reference_links/
    ├── reference_link_benchmarks/
    ├── manifests/
    │   └── resource_index.json
    ├── runs/
    └── cache/
```

Stage paths preserve each asset's source-relative `markdown_path`.

## Stages

| Stage | Adds | Authority |
|---|---|---|
| 1 | Readable Markdown, semantic anchors | `metadata/blocks/*.json` |
| 2 | Resolved legal citations | citation sidecars |
| 3 | Backward-reference descriptions and target registry | structure-discovery sidecars |
| 4 | Exact links to target blocks | `metadata/reference_links/*.json` |

Stages are immutable projections. A later stage does not replace earlier
metadata.

## Asset identity

Use `source_object_key` plus `source_sha256`. Do not use a basename or absolute
local path as portable identity.

`metadata/manifests/resource_index.json` indexes API resources by resource
family plus public ID, preserves every mirrored JSON revision, and selects the
highest revision suffix explicitly. Normalized metadata records preserve field
presence, source hash, and selected revision.

Keep these roles separate:

- `api_resource_type`: `dockets`, `documents`, or `comments`;
- `logical_document_role`: regulatory document, form comment, or attachment;
- `representation_role`: metadata JSON, HTML body, original, or extraction.

An asset record includes fields such as:

```json
{
  "source_object_key": "raw-data/.../comments/COMMENT.json",
  "source_sha256": "...",
  "source_role": "comment_metadata",
  "markdown_path": "raw-data/.../comments/COMMENT.json.md",
  "selection_reason": "...",
  "structure_status": "..."
}
```

## Semantic blocks

`metadata/blocks/<asset-hash>.json` records ordered blocks:

```json
{
  "block_id": "paragraph-0007",
  "block_type": "paragraph",
  "order": 7,
  "parent_section_id": "section-0002",
  "heading_context": ["..."],
  "plain_text": "..."
}
```

Block IDs are stable only within one document version. Globally identify a
block by asset identity/version plus `block_id`.

## Comments and attachments

A form comment and each attachment are separate logical documents. Pairing
metadata links them; do not merge them or count file formats as comments.

Prefer the original attachment for provenance and the derived extraction for
searchable text. Extraction is not byte- or layout-equivalent to the original.

## Citation sidecars

Citation candidates preserve detected text and spans. Resolved citation records
add normalized targets, URLs, titles, and status. Rendered Markdown links are
not the authoritative citation store.

## Backward references

Stage 3 identifies a comment passage that refers to an allowed target and
describes what to find. It does not resolve an exact target block.

```json
{
  "source_block_id": "paragraph-0007",
  "target_key": "document:CMS-2026-1255-0001",
  "search_description": "the proposed seven-day deadline"
}
```

The target registry is derived from source metadata. For comments,
`commentOnDocumentId` usually fixes the regulatory document target before any
model call.

## Exact links

Stage 4 resolves references against one complete target context. A link records:

```json
{
  "reference_id": "reference-...",
  "status": "linked | no-match | ambiguous",
  "source_block_id": "paragraph-0007",
  "target_key": "document:CMS-2026-1255-0001",
  "targets": [
    {
      "target_block_id": "paragraph-0142",
      "target_role": "primary | supporting"
    }
  ],
  "relationship": {},
  "provider_metadata": {}
}
```

Relationship classes are:

- `explicit_open_question`;
- `implicit_assumption_challenge`; and
- `other_substantive_relationship`.

Topical similarity is not enough. Keep primary and supporting targets distinct.
Retain no-match, ambiguous, rejected, and failed cases.

## Benchmarks

Benchmark output is isolated under `metadata/reference_link_benchmarks/` and
must not overwrite production Stage 4. Compare providers only on the same:

- cohort/source manifest;
- target `context_sha256`; and
- `reference_id` coverage.

Rejected batches are adjudication data, not no-match results.

## Core rules

1. Read sidecars for state, provenance, spans, and relationships.
2. Preserve source hashes and schema/linker versions.
3. Never silently repair source or extraction text.
4. Never force a reference link.
5. Never combine results from different target-context hashes.
6. Keep raw mirror, derived files, and Markdown output separate.

## Status

Use the status tool instead of counting files:

```shell
.venv/bin/python scripts/pipeline_status.py \
  --markdown-db data/markdown_db \
  --runtime-directory /tmp
```

Use `--json` for automation.

## Related guides

- [Corrected Mirrulations storage and JSON](MirrulationsStructureCorrected.md)
- [Regulatory resource traversal](MirrulationsRegulatoryDocumentStructure.md)
- [Regulatory process metadata](RegulationsGovRegulatoryProcessMetadata.md)