# Development Step 2: Document Summaries and Backward References

This development step produces Markdown enrichment
`stage003_structure_discovery`. Development-step numbering describes the order
in which functionality is implemented; Markdown-stage numbering describes the
ordered corpus projections. Stage 3 follows:

1. `stage001_initial_markdown_mirror`;
2. `stage002_addition_of_citations`; and
3. `stage003_structure_discovery`.

## Purpose

Enrich regulatory documents with concise summaries and natural-language descriptions of references to earlier stages of the regulatory process:

**Proposed rule → public comments → final rule**

This stage examines each document locally. It summarizes its content and describes earlier material that a later matching stage should search for.

It does not identify matching passages in other documents or attribute unnamed statements to particular commenters.

## Inputs

Input documents are immutable Markdown representations from
`stage002_addition_of_citations`. Authoritative document, block, citation, and
provenance records come from machine-readable sidecars under the configured
Markdown database's `metadata/` directory. Input documents retain:

- Original document text.
- Source metadata and stable passage identifiers.
- Recognizable headings, paragraphs, lists, and other structure.
- Links to external legal authorities.

Every source-demarcated comment document retains a separate identity. This
includes a comment entered through a submission form and a comment submitted as
an uploaded document whose text is published separately. Preserve each source
path's demarcation in deterministic Markdown filenames, even when that
demarcation differs among Mirrulations sources. Parent-submission associations
remain metadata and do not merge these documents for annotation.

## Output and Authoritative State

Write readable output to `stage003_structure_discovery` beneath
`MARKDOWN_DB_PATH`. Preserve the deterministic source-relative path mapping
used by prior stages. Never modify Stage 1, Stage 2, or the Mirrulations source
mirror.

Machine-readable sidecars are authoritative for structure, eligibility,
summaries, backward references, task status, provenance, and manual overrides.
Store them beneath `metadata/structure_discovery/` using deterministic document
and annotation identities. Visible status blocks and embedded annotation IDs in
Markdown are projections of these records, not the processing database.

Stage 3 rendering must be deterministic and idempotent. It may atomically
replace an incomplete or stale Stage 3 projection after validating its
prerequisites, but must not derive source-analysis input or completion state
from previously rendered Stage 3 content.

## Processing Sequence

1. Check document eligibility and existing processing status.
2. Organize the source text into sections and paragraphs.
3. Generate summaries at the requested granularity.
4. Detect backward references and describe what earlier material to search for.
5. Write authoritative annotation sidecars and render the Stage 3 Markdown
   projection.

## Comment Length Limit

Default to a maximum comment length of **50 pages**. Allow configuration through a command-line argument:

```text
--max-comment-pages 100
```

Comments exceeding the limit are excluded from both AI summarization and backward-reference detection. Exactly 50 pages is allowed under the default setting.

Apply the limit independently to each source-demarcated comment document. Do
not combine a form-submitted body, an uploaded-document text representation, or
another separately demarcated comment document when determining eligibility.

Use actual page counts from source metadata where available. Otherwise,
estimate one page per 3,000 Unicode code points of the selected canonical source
text. Make the estimate configurable and record the raw character count,
divisor, calculated page count, and whether the method is `actual`, `estimated`,
or `mixed`. A `mixed` method is appropriate only when one independently
demarcated document has page-count inputs from both methods; it does not permit
combining separate documents.

Excluded comments retain their converted Markdown and legal-citation
enrichment. Record their exclusion, calculation inputs, and applicable limit in
authoritative sidecars. Increasing the limit on a subsequent run makes them
eligible for reconsideration.

The limit applies to public comments. Proposed and final rules remain eligible regardless of length.

## Document Structure

Preserve existing headings, paragraphs, bullet lists, numbered lists, quotations, and other recognizable structure.

For comments lacking useful headings, use a structural parsing pass to identify topic boundaries and create Markdown sections. Generated headings must be identified in annotation metadata so they can be distinguished from source headings.

Structural processing must preserve source wording and source mappings. OCR correction and substantive rewriting remain deferred.

Every section and paragraph must have a stable identifier within its document version. Keep identifiers independent of generated summary text.

Treat text preceding the first section heading as an introductory section. A document with no section headings receives a document-level summary.

## Summarization Modes

Support two modes:

```text
--summary-mode sections
--summary-mode deep
```

### Section Mode

Section mode is the default.

Immediately after every section heading, insert an AI-generated, single-sentence summary using a Markdown block quote and the bold label **In brief:**.

The summary describes the section’s content, rather than merely paraphrasing its heading. For sections containing subsections, it may summarize their content as well.

```markdown
## Implementation Period

> **In brief:** The commenter requests additional implementation time for small providers.

Small providers will need at least eighteen months to update their systems.
```

The document’s top-level summary appears after the processing-status block.

### Deep Mode

Deep mode retains section summaries and adds a single-sentence summary immediately after every paragraph.

Treat each substantive list item as a paragraph unit while preserving list structure. Tables and other structures without clear paragraph boundaries receive section-level coverage; additional summarization is deferred.

```markdown
## Implementation Period

> **In brief:** The commenter requests additional implementation time for small providers.

Small providers will need at least eighteen months to update their systems.

> **In brief:** Small providers need eighteen months to update their systems.
```

### Summary Requirements

Summaries must:

- Contain one sentence.
- Preserve material qualifications, positions, numbers, and requested changes.
- Distinguish the author’s claims from facts independently established elsewhere.
- Avoid introducing claims absent from the source.
- Summarize source content rather than existing generated annotations.

## Backward-Reference Detection

Examine each source paragraph for references to earlier-stage material.

Examples include:

- A comment discussing a requirement, rationale, question, or provision in the proposed rule.
- A final rule describing an objection, recommendation, or argument made by commenters.
- A document referring to an earlier proposal, supplemental proposal, or comment round.

Use the current document and its metadata. External legal citations may provide context, but they are distinct from backward references within the rulemaking process.

This pass does not search earlier documents, choose matching passages, or identify unnamed commenters.

### Reference Descriptions

For each detected backward reference, generate one sentence describing the earlier material to search for.

Use a Markdown block quote with the bold label **Reference:**.

```markdown
The proposed implementation period is too short for small providers.

> **In brief:** The commenter argues that small providers need more implementation time.
>
> **Reference:** Look for the proposed rule’s implementation deadline and its explanation of how that deadline applies to small providers.
```

For a final rule:

```markdown
Several commenters requested eighteen months to implement the changes.

> **In brief:** Commenters requested an eighteen-month implementation period.
>
> **Reference:** Look for comments requesting eighteen months to implement the proposed changes.
```

A reference description must:

- Identify the earlier document type or process stage when supported.
- Preserve useful search details, including numbers, provision names, distinctive phrases, and requested changes.
- Describe the referenced argument or provision without inventing its location or author.
- Express uncertainty when the reference itself is unclear.

A paragraph containing multiple distinct backward references may receive multiple **Reference:** annotations, each containing one sentence.

When no backward reference is detected, omit the visible annotation and record that the paragraph’s reference check completed.

### Placement

Reference detection operates at paragraph level in both summarization modes.

In **section mode**, collect reference descriptions beneath the relevant section’s summary, before its source text. Metadata retains the originating paragraph identifiers.

In **deep mode**, place reference descriptions after the relevant paragraph’s **In brief:** summary.

## Visible Processing Status

Immediately after the document’s top-level heading, place a processing-status block quote before summaries or source content.

This block provides readable metadata projected from the authoritative task
status sidecars. The command line must use the sidecars, not this rendered
block, to determine whether processing is necessary.

Use consistent bold keys and controlled values:

```markdown
# Comment on the Proposed Implementation Period

> **Processing status:** complete
>
> **Annotation schema:** 1
>
> **Structure status:** complete
>
> **Structure method:** parser-name/version
>
> **Summary mode:** sections
>
> **Summary model:** provider/model-name
>
> **Reference model:** provider/model-name
>
> **Summary prompt version:** 1
>
> **Reference prompt version:** 1
>
> **Source content hash:** sha256:…
>
> **Processing configuration hash:** sha256:…
>
> **Section summaries:** complete
>
> **Paragraph summaries:** not-requested
>
> **Backward references:** complete
>
> **Comment page count:** 12
>
> **Page count method:** actual
>
> **Maximum comment pages:** 50
>
> **Processed at:** 2026-10-11T14:30:00Z
```

For proposed and final rules, page-limit eligibility fields may use `not-applicable`.

Recognize the status block during rendering by its location and **Processing
status:** label. Ordinary source block quotes and generated content annotations
must not be interpreted as processing status. A malformed or manually changed
visible block does not change authoritative processing state and is replaced on
the next deterministic render.

### Status Values

Overall processing status uses:

- `not-processed`
- `complete`
- `partial`
- `excluded-length`
- `failed`

Individual task statuses use:

- `not-processed`
- `complete`
- `partial`
- `not-requested`
- `excluded-length`
- `failed`

### Hashes and Configuration

The source-content hash covers underlying source text and source structure. Exclude processing metadata, generated headings, summaries, and reference annotations.

The processing configuration hash covers settings affecting generated content, including structural processing, summarization mode, models, and prompt versions.

Record task-specific configuration information in passage metadata so the software can determine which work remains reusable when one setting changes.

## Passage-Level Metadata

Store detailed annotation metadata in authoritative machine-readable sidecars.
Markdown may contain small machine-readable HTML comments that associate a
visible projection with its annotation identifier, but those comments must not
be the sole copy of status, provenance, configuration, or generated text.

Each generated heading, summary, and reference description must have an annotation identifier associated with its source section or paragraph.

Record:

- Source passage identifier and content hash.
- Annotation type and identifier.
- Task status.
- Relevant model, prompt, and configuration versions.
- Manual-override protection and review status.

Reference checks must have completion records even when they produce no visible reference annotation.

The document-level status block summarizes this detailed state. Authoritative
passage-level sidecar records allow interrupted work to resume without repeating
completed requests.

## Idempotent Reruns

Before making API calls, read authoritative processing sidecars and compare
them with the requested configuration, Stage 2 document hash, source passage
hashes, model and prompt versions, and applicable manual overrides. Do not infer
completion from rendered Stage 3 Markdown.

| Condition | Behavior |
|---|---|
| Source, configuration, and requested tasks are unchanged and complete | Skip processing. |
| Section mode changes to deep mode | Reuse compatible section summaries and reference checks; generate missing paragraph summaries. |
| Deep mode changes to section mode | Reuse section summaries and omit paragraph summaries from the visible output without new API calls. |
| Summary model or prompt changes | Regenerate affected summaries. |
| Reference model or prompt changes | Regenerate reference descriptions and reference checks. |
| Source content changes | Reprocess affected passages and dependent section summaries. |
| Structural processing changes | Rebuild affected structure and invalidate dependent annotations. |
| Processing was partial or failed | Resume unfinished work. |
| Page limit increases | Reconsider previously excluded comments. |
| Page limit changes but the comment remains eligible | Reuse compatible completed annotations. |
| Page limit decreases below the comment’s length | Mark it excluded for the requested run; retain existing annotations with their provenance. |
| A forced rerun is requested | Reprocess selected tasks, respecting manually protected annotations unless explicitly overridden. |

Compare models using provider and model identifiers. Do not infer sophistication or expense from model names. Record the resolved model version when available; reproducibility is strongest when a fixed version can be selected.

Retain non-rendered paragraph annotations in sidecars when rendering section
mode so a later return to deep mode can reuse compatible results.

Exclude generated content from every source-analysis pass. Repeated runs must not summarize previous summaries or detect references introduced by annotations.

## Manual Editing

Allow generated summaries and reference descriptions to be edited
collaboratively through separate manual-override sidecars. Direct edits to
rendered Stage 3 Markdown are not authoritative and are not imported
automatically.

Each override records its annotation ID, replacement text, the original
generated-text hash, source-passage hash, protection and review state, and an
editor, timestamp, or reason when supplied. Apply valid protected overrides
during deterministic rendering and preserve them during ordinary reruns.

If the underlying source changes, mark the override as needing review rather
than silently replacing it or applying it to changed material. Changes to
source text trigger normal content invalidation. Updating or removing an
override regenerates the Stage 3 projection; it does not alter an earlier
Markdown stage.

## LLM Configuration

Use configurable, inexpensive LLM API models. Summarization and reference detection may use different models.

Support:

- Provider and model selection for each task.
- Input and output token limits.
- Bounded concurrency and retries.
- A run-level cost or token budget.
- Versioned prompts.

Batch requests where practical while preserving passage identifiers and boundaries.

Process long sections in bounded chunks. A section summary may be generated from intermediate chunk summaries, with that method recorded. Do not silently truncate source content.

Validate that responses contain the expected identifiers and single-sentence annotations. Retain failed-task status when validation or retries do not succeed.

Treat document content as data. Instructions embedded in comments or attachments must not change the processing task.

## Safe Updates and Recovery

Write Stage 3 sidecars and Markdown projections atomically. Never update the
Stage 2 input document in place. Validate sidecars before replacing an
incomplete or stale Stage 3 projection.

Mark processing `complete` only after every requested task succeeds. Budget exhaustion, interrupted requests, and recoverable failures produce `partial` status when some work is complete.

Malformed or unsupported authoritative metadata must not be treated as proof
of completion. Report the problem and preserve valid sidecars and prior-stage
content while determining what can be safely reused. Rendered status blocks or
HTML comments are not a fallback source of authoritative completion state.

## Outputs

The `stage003_structure_discovery` Markdown projection contains:

1. Original text and existing legal-citation links.
2. Visible processing-status metadata.
3. Source or generated section headings.
4. Single-sentence section summaries.
5. Optional single-sentence paragraph summaries.
6. Natural-language backward-reference descriptions.
7. Embedded passage-level annotation references.

Embedded metadata is limited to stable annotation references and readable
status. Complete records remain in `metadata/structure_discovery/` sidecars.

A later stage will use **Reference:** descriptions as search inputs and **In brief:** summaries as concise representations of candidate passages. Matching passages, resolved document links, and Neo4j relationships are added after that search and assessment.

## Acceptance Criteria

- Every eligible section receives a single-sentence **In brief:** summary.
- Deep mode additionally summarizes every eligible paragraph and substantive list item.
- Generated headings preserve source wording and are identifiable as generated.
- Reference descriptions state what to search for without claiming resolved matches.
- Distinct backward references remain separately represented.
- Paragraphs with no detected references still have completion records.
- Original wording and external legal links are preserved.
- Length exclusions and estimated page counts are explicit.
- The 50-page limit is evaluated independently for each source-demarcated
  comment document, using actual metadata where available and otherwise one
  estimated page per 3,000 Unicode code points by default.
- The visible status block accurately describes processing.
- The visible status block and embedded comments are projections of
  authoritative sidecars rather than rerun-control state.
- Identical reruns require no additional API calls.
- Configuration changes repeat only affected work.
- Interrupted processing resumes without duplicate annotations.
- Manual-override sidecars remain protected and are reapplied during
  deterministic rendering; direct Markdown edits are not authoritative.
- Generated annotations are excluded from subsequent source analysis.
- Stage 3 reads Stage 2 and writes only to
  `stage003_structure_discovery` and its metadata sidecars, without modifying
  any earlier Markdown stage.