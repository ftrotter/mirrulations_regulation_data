# Rich Document Structure

This document is an orientation and data-contract guide for humans and language
models performing bespoke analysis in this repository. It describes the
generated Markdown database, the progressively enriched document versions, and
the authoritative metadata used to connect public comments to regulatory
actions.

The most important rule is:

> **Machine-readable metadata is authoritative. Markdown is a readable,
> deterministic projection of that metadata.**

Do not infer processing state, provenance, citation spans, or relationship
semantics solely by parsing rendered Markdown when an authoritative sidecar is
available.

## Core regulatory relationships

The corpus represents a regulatory process such as:

```text
proposed rule → public comments → final or later regulatory action
```

The current Stage 4 work links passages in public comments back to exact
semantic blocks in the proposed rule on which they comment.

For analytical purposes, comments may relate to a regulatory action in three
principal ways:

1. `explicit_open_question`: the comment responds to an agency request for
   comment, feedback, information, or consideration.
2. `implicit_assumption_challenge`: the comment disputes a stated or unstated
   premise embodied in the agency's reasoning, estimate, expected outcome,
   scope, implementation account, causal claim, or proposed design.
3. `other_substantive_relationship`: another concrete relationship, such as
   support, opposition, implementation advice, a legal objection, a requested
   modification, or an alternative proposal.

Explicit agency questions are deliberately made prominent, or "skylined," in
the full-context linker. Mere topical similarity is never sufficient for a
link.

## Source mirror versus Markdown database

Two separate trees have different purposes:

- The **Mirrulations source mirror** is pipeline input. It preserves the
  published `raw-data/` and `derived-data/` hierarchy and must not contain
  generated annotations, logs, caches, or Markdown stages.
- The **Markdown database** is generated output. Its default location is
  `data/markdown_db/`, controlled by `MARKDOWN_DB_PATH`.

These roots must not overlap. Never edit source files as a way to change an
enriched result. Never write generated artifacts into the source mirror.

## Markdown database directory structure

The principal layout is:

```text
data/markdown_db/
├── stage001_initial_markdown_mirror/
│   ├── raw-data/...
│   └── derived-data/...
├── stage002_addition_of_citations/
│   ├── raw-data/...
│   └── derived-data/...
├── stage003_structure_discovery/
│   ├── raw-data/...
│   └── derived-data/...
├── stage004_backward_reference_links/
│   ├── raw-data/...
│   └── derived-data/...
└── metadata/
    ├── blocks/
    ├── annotations/
    │   ├── citation_candidates/
    │   └── citations/
    ├── structure_discovery/
    │   └── annotations/
    ├── reference_links/
    ├── reference_link_benchmarks/
    ├── manifests/
    ├── runs/
    └── cache/
```

Stage paths preserve the source-relative identity beneath `raw-data/` or
`derived-data/`. Given an asset's `markdown_path`, its readable Stage 2 path is:

```text
<MARKDOWN_DB_PATH>/stage002_addition_of_citations/<markdown_path>
```

The same rule applies to the other numbered stages.

## Document identities

The corpus contains several kinds of separately identified documents:

- agency regulatory documents, including proposed rules;
- form-submitted comment bodies;
- uploaded comment attachments represented by extracted text;
- other docket documents and their readable derivatives.

A submission body and an attachment remain separate document identities even
when they belong to the same Regulations.gov submission. Do not concatenate or
silently merge them. Parent-submission relationships belong in metadata.

The stable cross-stage identity is the asset's `source_object_key`. Important
asset fields include:

```json
{
  "source_object_key": "derived-data/.../comments/...txt",
  "source_sha256": "...",
  "markdown_path": "derived-data/.../comments/...txt.md",
  "selection_reason": "readable-text-representation",
  "source_role": "markdown-source",
  "source_suffix": ".txt",
  "content_location": null,
  "structure_status": "not-applicable"
}
```

Do not use a filename alone as document identity. Preserve the complete object
key and source hash in analytical outputs.

## Shared semantic-block structure

Comments and regulatory documents are normalized into ordered semantic blocks.
The supported block types are:

- `section`
- `paragraph`
- `list`
- `quotation`
- `label`
- `table`

Typical block metadata is:

```json
{
  "block_id": "paragraph-0077",
  "block_type": "paragraph",
  "order": 84,
  "plain_text": "...",
  "parent_section_id": "section-0004",
  "heading_context": [],
  "normalization": {
    "removed_nul_code_points": 0
  }
}
```

Depending on the source and extraction method, a block can also contain:

- `heading_level`;
- `items` for a list;
- `rows` for a table;
- `source_start` and `source_end` character offsets;
- `page_start` and `page_end`;
- alignment method and confidence fields.

Rendered blocks begin with an HTML anchor:

```markdown
<a id="paragraph-0077"></a>

The block's text follows the anchor.
```

### Semantic-ID scope

Semantic IDs are stable within one immutable document version, but they are not
globally unique. For example, many documents contain `paragraph-0001`.

Always identify a passage with at least:

```text
source_object_key + source_sha256 + block_id
```

For a regulatory-action target, use:

```text
target_document_id + target document version/hash + target_block_id
```

Never transfer a block ID from one document to another merely because its text
or numbering looks similar.

## Stage 1: initial Markdown mirror

Directory:

```text
stage001_initial_markdown_mirror/
```

Stage 1 is the first readable Markdown representation of the selected source.
It preserves source wording while exposing semantic block anchors and readable
structure. It does not add resolved legal-citation links, Stage 3 summaries, or
Stage 4 regulatory-action links.

Both comments and regulatory documents use the shared semantic-block format.
The difference is their role, not their basic Markdown contract:

- A **comment** contains stakeholder positions, recommendations, evidence, and
  reactions to the agency action.
- A **regulatory document** contains background, agency reasoning, proposed or
  operative provisions, explicit requests for comment, and regulatory text.

For analysis requiring exact source wording, begin with `plain_text` in the
block sidecar or the corresponding Stage 1 block. Do not use text from generated
summaries as a substitute for source text.

## Stage 2: citation-enriched Markdown

Directory:

```text
stage002_addition_of_citations/
```

Stage 2 is rendered from Stage 1 plus authoritative citation sidecars. It adds
links for resolved legal authorities while preserving semantic block IDs and
source-relative document paths.

An abbreviated rendered block may look like:

```markdown
<a id="paragraph-0014"></a>

The agency acted under
[5 U.S.C. § 553](https://www.law.cornell.edu/uscode/text/5/553).
```

Stage 2 is the immutable readable input for Stage 3. Stage 3 must not alter
Stage 2.

### Citation offsets

Citation `start` and `end` values are Unicode code-point offsets into a block's
unlinked `plain_text`. The end offset is exclusive. Do not calculate offsets
against Markdown containing inserted links.

Unresolved or competing citations can remain plain text in Markdown while
remaining inspectable in metadata.

## Stage 3: structure discovery

Directory:

```text
stage003_structure_discovery/
```

Stage 3 analyzes coherent document segments and records:

- document eligibility;
- section or passage summaries;
- whether reference detection was requested and completed;
- backward references from later-process documents to known earlier targets;
- precise natural-language `search_description` values.

Stage 3 does **not** resolve a backward reference to an exact block in another
document. It states what passage a later linker should find.

An abbreviated comment projection can contain:

```markdown
<a id="paragraph-0011"></a>

The commenter responds to the agency's request for information.

> **Reference:** Look in this proposed rule CMS-0062-P
> (Regulations.gov document CMS-2026-1255-0001) for the request for
> information on streamlining step therapy and using treatment history.
```

Visible summaries or status blocks are projections. Use
`metadata/structure_discovery/annotations/` to determine completion and extract
references.

### Backward-reference meaning

A backward reference should identify a concrete passage in an earlier
regulatory document, such as a:

- provision or proposed requirement;
- deadline or numerical standard;
- definition;
- agency rationale;
- explicit open question or request for information;
- requested change.

General praise, docket headers, salutations, author credentials, and broad
topical similarity are not sufficient.

## Stage 4: exact backward-reference links

Production projection directory:

```text
stage004_backward_reference_links/
```

Production sidecars:

```text
metadata/reference_links/
```

Stage 4 resolves each Stage 3 backward reference to exact semantic target IDs
in the metadata-selected regulatory document. It can return:

- `linked`;
- `no-match` in rendered production sidecars, corresponding to `no_match` in
  the strict model schema; or
- `ambiguous` in premium comparison results.

The Markdown projection adds links after the originating comment block:

```markdown
> **Linked regulatory-action passage:**
> [paragraph-0777](../../.../documents/proposed-rule.md#paragraph-0777)
```

Primary and supporting targets are both readable links in Markdown. Their
different roles are preserved in metadata, not in the visible label.

Stage 4 currently enriches comments by linking them to regulatory-action
blocks. Do not assume that every regulatory document itself receives a Stage 4
Markdown copy.

## Comment structure versus regulatory-document structure

### Comments

Comment structure can include:

- a form-submitted body;
- letter headings, organization descriptions, and signatures;
- section headings and recommendations;
- extracted page numbers or footnotes;
- lists of requested policy changes;
- citations to law, research, or other comments;
- one or more Stage 3 backward references per block.

Comments may be noisy because PDF and DOCX extraction can preserve page numbers,
broken lines, or imperfect layout. Use alignment metadata and source offsets
where available. Do not "repair" source wording silently.

### Regulatory documents

Regulatory documents can contain:

- procedural and statutory background;
- descriptions of earlier rules;
- agency assumptions and estimates;
- proposed policy and implementation details;
- summaries of proposals;
- explicit solicitations for comment;
- labeled Requests for Information;
- codified regulatory text, tables, and incorporation-by-reference material.

When linking a comment, distinguish:

- current proposal from historical background;
- agency rationale from operative requirements;
- a broad section heading from the substantive paragraph;
- an explicit question from nearby explanatory context;
- primary target blocks from supporting blocks.

The entire regulatory document is available to premium Stage 4 models. Lexical
retrieval is a baseline and diagnostic, not a constraint on the full-context
model.

## Metadata file naming and joins

Most per-document metadata files use:

```text
sha256(source_object_key) + ".json"
```

The same basename is normally shared across:

```text
metadata/blocks/<hash>.json
metadata/annotations/citation_candidates/<hash>.json
metadata/annotations/citations/<hash>.json
metadata/structure_discovery/annotations/<hash>.json
metadata/reference_links/<hash>.json
```

Do not rely only on basename matching. Verify the embedded
`asset.source_object_key` and `asset.source_sha256` before joining records.

The principal joins are:

```text
asset.source_object_key
  ↕
asset.markdown_path
  ↕
semantic block_id within that asset
  ↕
Stage 3 source_block_id
  ↕
Stage 4 reference_id and target_block_id
```

## Block metadata sidecars

Directory:

```text
metadata/blocks/
```

The block sidecar is the canonical machine-readable representation of a
selected document. Its top-level shape is:

```json
{
  "schema_version": 1,
  "asset": {},
  "document_metadata": {},
  "pairing": null,
  "alignment": {},
  "target_registry": [],
  "blocks": []
}
```

Fields can be absent or `null` when they do not apply. Important components are:

- `asset`: provenance and output-path identity;
- `document_metadata`: friendly or source-supplied document information;
- `pairing`: a relationship to an extracted attachment or parent record;
- `alignment`: extraction and page-alignment information;
- `target_registry`: regulatory actions this document may refer back to;
- `blocks`: ordered semantic source content.

Use `blocks` rather than reparsing Markdown when block text, order, type, or
source location is required.

## Citation-candidate sidecars

Directory:

```text
metadata/annotations/citation_candidates/
```

Top-level shape:

```json
{
  "schema_version": 1,
  "candidates": []
}
```

A candidate can include:

```json
{
  "schema_version": 1,
  "document_version": "source sha256",
  "block_id": "paragraph-0014",
  "start": 100,
  "end": 116,
  "matched_text": "42 C.F.R. § 422",
  "citation_family": "cfr",
  "normalized_target": "cfr:42:422",
  "structured_components": {},
  "adapter_name": "eyecite",
  "adapter_version": "...",
  "warnings": []
}
```

These are raw or normalized adapter findings. They are not necessarily the
final reconciled citation annotations.

## Reconciled citation sidecars

Directory:

```text
metadata/annotations/citations/
```

Top-level shape:

```json
{
  "schema_version": 1,
  "citations": []
}
```

Resolved records can add:

- `annotation_id`;
- `supporting_adapters`;
- `resolution_status`;
- `destination_provider`;
- `destination_url`;
- `link_precision`;
- `url_verification_status`.

Keep `resolution_status` separate from URL verification. A conventionally known
URL can be unverified, and an HTTP success does not prove target identity.

## Stage 3 structure-discovery sidecars

Directory:

```text
metadata/structure_discovery/annotations/
```

Top-level shape:

```json
{
  "schema_version": 2,
  "asset": {},
  "configuration_hash": "...",
  "eligibility": {},
  "target_registry": [],
  "annotations": []
}
```

Eligibility records include:

```json
{
  "eligible": true,
  "page_count": 12,
  "page_count_method": "actual",
  "character_count": 35000,
  "maximum_comment_pages": 50,
  "exclusion_reason": null
}
```

Regulatory documents use a `not-applicable` page-count method. A comment can be
excluded for length or because a form body is only an attachment placeholder.

A block annotation has the form:

```json
{
  "block_id": "paragraph-0011",
  "task_hash": "...:paragraph-0011",
  "segment_task_hash": "...",
  "task_status": "complete",
  "summary": "Analyzed in its surrounding document context.",
  "reference_check_requested": true,
  "render_summary": false,
  "placement": "after-block",
  "backward_references": []
}
```

A backward reference contains:

```json
{
  "source_block_id": "paragraph-0011",
  "target_key": "document:CMS-2026-1255-0001",
  "target": {
    "document_ids": ["CMS-2026-1255-0001"],
    "docket_id": "CMS-2026-1255",
    "agency_rule_identifier": "CMS-0062-P",
    "document_type": "Proposed Rule",
    "title": "..."
  },
  "search_description": "the precise passage to find"
}
```

`search_description` is a search objective, not a resolved target and not a
summary of the whole comment.

## Production Stage 4 link sidecars

Directory:

```text
metadata/reference_links/
```

Top-level shape:

```json
{
  "schema_version": 2,
  "linker_version": 1,
  "provider": "google",
  "model": "gemini-3.1-pro-preview",
  "context_sha256": "...",
  "asset": {},
  "links": []
}
```

Each link preserves the Stage 3 identity fields plus the full semantic result:

```json
{
  "reference_id": "reference-...",
  "status": "linked",
  "source_block_id": "paragraph-0011",
  "target_key": "document:CMS-2026-1255-0001",
  "search_description": "...",
  "confidence": 0.93,
  "rationale": "...",
  "relationship": {},
  "targets": [],
  "provider_metadata": {}
}
```

The `reference_id` is deterministic for the source object key, source block,
target key, and search description.

### Relationship object

The strict relationship object is:

```json
{
  "reference_id": "reference-...",
  "primary_relationship_class": "explicit_open_question",
  "secondary_relationship_classes": [
    "other_substantive_relationship"
  ],
  "match_status": "linked",
  "primary_target_ids": ["paragraph-0777"],
  "supporting_target_ids": ["paragraph-0775"],
  "open_question_ids": ["open-question-60bb959460f9"],
  "confidence": 0.93,
  "relationship_evidence": {
    "comment_position": "...",
    "agency_position": "...",
    "link_explanation": "..."
  }
}
```

Consistency requirements include:

- `linked` requires a primary target;
- `no_match` cannot contain target or open-question IDs;
- primary and supporting IDs cannot overlap;
- all IDs must exist in the selected target version;
- a linked `explicit_open_question` requires an `open_question_id`;
- that open-question ID must correspond to a selected primary question block.

### Target object

Each flattened target record contains:

```json
{
  "target_document_id": "CMS-2026-1255-0001",
  "target_block_id": "paragraph-0777",
  "target_role": "primary",
  "stage_2_path": "/absolute/path/to/stage002/...md"
}
```

`stage_2_path` is useful for rendering but should not replace portable document
identity in exported analysis.

### Provider metadata

Provider metadata records can include:

- response ID and returned model version;
- request latency;
- input and output tokens;
- cache creation/write tokens;
- cache-read tokens;
- reasoning or thought tokens;
- total tokens.

Field names differ because provider APIs expose different usage categories.
Normalize deliberately when comparing cost or cache behavior.

## Open-question index and full-target serialization

The premium linker serializes the complete regulatory target deterministically.
It places an open-question index before all substantive semantic blocks:

```text
TARGET DOCUMENT
Document ID: CMS-2026-1255-0001
OPEN QUESTION INDEX
[{...}]
SEMANTIC BLOCKS
<block id="paragraph-0777" type="paragraph"
 discourse_role="explicit_open_question"
 open_question_id="open-question-60bb959460f9">
...
</block>
```

An open-question record contains:

```json
{
  "open_question_id": "open-question-60bb959460f9",
  "question_target_ids": ["paragraph-0777"],
  "supporting_target_ids": ["paragraph-0776"],
  "question_text": "..."
}
```

Open-question detection is intentionally conservative. A historical sentence
that merely mentions an earlier Request for Information is not automatically a
current agency question.

The `context_sha256` identifies the exact serialized target context supplied to
a premium provider. Results produced against different context hashes must not
be silently combined.

## Cross-provider benchmark metadata

Benchmark artifacts are isolated from production Stage 4:

```text
metadata/reference_link_benchmarks/
├── benchmark-50-comments/
│   ├── manifest.json
│   └── source_object_keys.json
├── google/<model>/<context_sha256>/
│   ├── manifest.json
│   ├── batches/
│   └── rejected_batches/
├── anthropic/<model>/<context_sha256>/...
└── openai/<model>/<context_sha256>/...
```

### Cohort manifest

A benchmark cohort manifest records:

- deterministic selection method;
- complete selected source-object keys;
- whole-comment count;
- total backward-reference count;
- reference-count distribution;
- useful selection signals.

If a benchmark says "50 comments," every Stage 3 reference in those 50 whole
comment documents belongs to the cohort. It does not mean only 50 references.

### Accepted batch checkpoint

Each successful provider batch is written atomically before later batches must
finish:

```json
{
  "schema_version": 1,
  "batch_number": 1,
  "provider": "anthropic",
  "model": "claude-opus-5-5",
  "context_sha256": "...",
  "links": []
}
```

Checkpoint filenames derive from the batch's reference IDs. Resumed runs reuse
accepted references without overwriting unrelated batches.

### Rejected batch checkpoint

If a provider returns valid structured JSON that fails semantic validation, the
response is retained for adjudication:

```json
{
  "schema_version": 1,
  "provider": "anthropic",
  "model": "claude-opus-5-5",
  "context_sha256": "...",
  "validation_error": "...",
  "response": {
    "results": []
  },
  "provider_metadata": {}
}
```

Rejected results do not count as accepted coverage. They are valuable evidence
for improving prompts, validators, and generalized hard-case fixtures.

## Manifests, runs, and global metadata

The `metadata/manifests/` directory records inventory, selection, verification,
source pairing, and JSON-normalization information. Examples include:

- source inventory and document-selection decisions;
- source pairings;
- verification records;
- original and normalized JSON hashes.

The `metadata/runs/` directory records run-level counts, adapter results,
failures, and latest-run state. These records explain how generated artifacts
were produced; they are not substitutes for per-document sidecars.

Global human-readable metadata can also include friendly-name and reverse-lookup
Markdown. Friendly display names do not change canonical IDs.

The `metadata/cache/` directory is for generated cache state. Treat caches as
rebuildable performance aids, not authoritative analytical results.

## Recommended bespoke-analysis workflow

### Analyze source content

1. Select documents by `asset.source_object_key`, docket metadata, and role.
2. Load `metadata/blocks/<hash>.json`.
3. Analyze ordered `plain_text` blocks with heading, parent-section, page, and
   alignment context.
4. Use a numbered Markdown stage only when human-readable links or projections
   are useful.

### Analyze comment-to-rule links

1. Load the Stage 3 annotation sidecar for each comment.
2. Enumerate every `backward_reference` and preserve its source block, target
   key, and search description.
3. Join to production links by deterministic `reference_id`, or reconstruct the
   Stage 3 identity tuple:
   `source_object_key`, `source_block_id`, `target_key`, and
   `search_description`.
4. Join each `target_block_id` to the target regulatory document's block
   sidecar.
5. Keep primary and supporting targets separate.
6. Analyze relationship class independently from match status.
7. Retain no-match, ambiguous, and rejected cases rather than forcing a link.

### Compare premium providers

1. Fix one cohort manifest and one `context_sha256`.
2. Load accepted checkpoints for each provider/model.
3. Intersect by `reference_id` before comparing results.
4. Compare at least:
   - primary relationship class;
   - linked/no-match/ambiguous status;
   - exact primary target IDs;
   - supporting target IDs;
   - open-question IDs;
   - confidence and explanation;
   - token/cache usage and latency.
5. Inspect rejected batches separately. Do not silently count them as model
   disagreement or no-match.
6. Convert recurring disagreements into general behavioral rubrics and
   synthetic regression fixtures, not docket-specific hard-coded links.

## Common analytical mistakes to avoid

- **Do not parse Markdown for authoritative state.** Read sidecars.
- **Do not treat block IDs as globally unique.** Pair them with document
  identity and version.
- **Do not merge a form comment and its attachment.** They are separately
  demarcated documents.
- **Do not confuse a Stage 3 search description with a Stage 4 resolved link.**
- **Do not treat broad topical overlap as a backward reference.**
- **Do not prefer historical discussion over the current proposal.**
- **Do not select an RFI heading when the substantive question paragraph is
  available.** A heading can be supporting context.
- **Do not infer an assumption challenge solely from the word `assume`.** The
  premise may be embodied in design, scope, estimates, or expected outcomes.
- **Do not collapse primary and supporting targets.** They answer different
  analytical questions.
- **Do not treat model confidence as calibrated probability.**
- **Do not combine provider results across different target context hashes.**
- **Do not overwrite production Stage 4 with benchmark output.** Promotion is a
  deliberate action.
- **Do not discard rejected structured responses.** They belong in the
  adjudication corpus.
- **Do not use an absolute `stage_2_path` as portable identity.** Use canonical
  asset and block IDs.
- **Do not silently repair extraction artifacts.** Preserve provenance and
  create a versioned derivative for any text transformation.

## Monitoring processing state

Use the repository status tool rather than hand-counting files:

```shell
.venv/bin/python scripts/pipeline_status.py \
  --markdown-db data/markdown_db \
  --runtime-directory /tmp
```

Use `--json` for machine-readable monitoring. Premium Stage 4 jobs appear under
`premium_benchmark_processes`, including provider, PID state, accepted unique
references, accepted batches, rejected batches, and latest log progress.

## Contract-maintenance guidance

This guide documents the current implemented structure; schema versions remain
authoritative. When changing a contract:

1. increment the relevant schema or linker version when compatibility changes;
2. preserve prior immutable stages and sidecars;
3. update renderers and validators together;
4. add or update regression tests;
5. update this document with the new paths, fields, and joining rules;
6. verify the result with `scripts/pipeline_status.py` and the full test suite.

Future analysis should remain rebuildable from source-identity records,
semantic blocks, and authoritative annotations. Human-readable Markdown should
make the corpus easy to inspect, but it must never become the only place where
meaning or provenance is stored.