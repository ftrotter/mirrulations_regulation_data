# Mirrulations document enrichment — starter specification

Status: proposed implementation specification, version 0.1.

## Approved first development milestone

The first end-to-end development run has three user-visible operations:

1. download a bounded Mirrulations selection with the existing `rclone`
   helper, including original files used as structural evidence;
2. create an initial Markdown version of every selected, applicable HTM, HTML,
   JSON, and TXT asset; and
3. create a second Markdown version that adds resolved legal citations as
   links.

For this milestone, citation mining, reconciliation, target resolution, and
rendering are one user-facing Markdown enrichment operation. They may remain
separate internal modules and sidecars so failures, provenance, and intermediate
decisions stay inspectable.

Original files are immutable structural evidence. For PDF-backed extracted TXT,
use pypdf to recover page, line, and paragraph evidence while preserving the
published Mirrulations extracted text as canonical wording. Record both source
objects and hashes. Do not add new OCR. DOCX and image structure recovery is
deferred and must receive an explicit structure-pending status.

## Purpose and scope

Begin with a verified byte-for-byte local acquisition of the selected
Mirrulations source objects. After verification, pretty-print downloaded JSON
in place for browsing while recording pre- and post-normalization hashes. Build
a reproducible corpus of regulatory
documents and comments as readable Markdown.

Enrich explicit legal citations through a common adapter interface backed by
multiple extraction libraries. When a specific target can be resolved, render
the citation as a link to Cornell's Legal Information Institute (LII). Use
other destinations as fallbacks.

Source fidelity is a non-negotiable prerequisite. For the selected scope, the
local source corpus must contain the exact bytes, filenames, and relative paths
published by Mirrulations. Use the repository's existing `rclone` command-line
tooling because it copies objects directly, without an application-specific
download or transformation layer.

We will focus the development one stage at a time. Do not execute against future stages until this one is complete.

The generated outputs must support these later extensions.

## Repository and local data layout

```text
SPEC.md
.gitignore
config/                         # Versioned configuration and examples
src/                            # Future implementation
tests/fixtures/                 # Small, versioned synthetic/test samples
data/                           # Entire directory excluded from Git
  source/mirrulations/          # Exact, read-only rclone mirror; source files only
  manifests/                    # Mirror verification and document inventories
  normalized/<document>/<version>/
    document.json               # Metadata and chosen source representation
    blocks.jsonl                # Addressable text blocks and source mapping
    document.md                 # Markdown before citation enrichment
  annotations/<document>/<version>/
    candidates.jsonl            # Findings from every adapter
    citations.jsonl             # Reconciled findings and resolved destinations
  enriched/<document>/<version>/document.md
  runs/<run-id>/                # Configuration, versions, counts, errors
  cache/                        # Resolver responses and URL checks
```

The approved readable Markdown layout supersedes the illustrative
`normalized/` and `enriched/` output locations above. Use a configurable
Markdown database root with immutable numbered stages:

```text
<MARKDOWN_DB_PATH>/
  stage001_initial_markdown_mirror/
    raw-data/...
    derived-data/...
  stage002_addition_of_citations/
    raw-data/...
    derived-data/...
  metadata/
    manifests/
    documents/
    blocks/
    annotations/
      citation_candidates/
      citations/
    runs/
    cache/
  logs/
```

`MARKDOWN_DB_PATH` defaults to the repository-relative
`./data/markdown_db/`. A value from the environment may select another target
directory. Resolve and validate both it and `MIRRULATIONS_DESTINATION_PATH`
before processing. Reject configurations where either path equals, contains,
or is contained by the other. Never edit an actual `.env` file; document the
setting in versioned example files.

Stage directories contain readable Markdown while `metadata/` contains the
authoritative manifests and sidecars. Map source object keys to stage output
paths deterministically and without collisions. Future development adds new
`stageNNN_*` directories and does not overwrite these two stages.

The `rclone` destination is a source mirror, not a workspace. It contains only
files copied from Mirrulations in their original hierarchy. Never write any of
the following into the mirror:

- manifests or logs;
- temporary files;
- normalized content;
- annotations; or
- any other generated artifact.

No pipeline stage may rename, move, rewrite, re-encode, reformat, decompress,
concatenate, or delete a mirrored source file. Create all generated-data
directories outside the mirror, as needed.

Treat non-JSON source objects as immutable. JSON normalization is the sole
approved in-place source transformation and occurs only after remote
verification. Record the verified original SHA-256 and normalized local SHA-256.
Every derivative must identify the exact local source bytes from which it was
produced.

A later Mirrulations change creates a new source version. It must never
silently alter the identity or provenance of an earlier run. If historical
bytes are required, preserve a content-addressed snapshot outside the active
mirror before refreshing it.

Generated artifacts remain outside Git. Schemas, configuration, and small
fixtures belong in Git.

## Stage 0: exact rclone mirror, verification, and inventory

### Exact source baseline

The first stage must establish an exact local source baseline for the selected
Mirrulations scope. "Exact" means the local mirror has the same:

- object bytes;
- filenames and filename case; and
- relative `raw-data/` and `derived-data/` paths.

No local transformation is permitted. Processing must not begin from
hand-copied, previously normalized, or otherwise altered substitutes.

### Required rclone workflow

Use the existing `scripts/rclone/mirrulations_downloader.py` command-line helper
and the setup documented in `scripts/rclone/README.md`. Requiring `rclone`
preserves source fidelity by avoiding application code between the published
objects and the local mirror.

Do not add any of the following to the enrichment application:

- a Python S3 client;
- HTTP download code; or
- another acquisition command.

Configure the helper's local `.env` and `rclone.config` from their example
files. The anonymous `myconfig:mirrulations/` remote provides access to the
public bucket. AWS credentials are not required.

### Acquisition scope

Select and record an explicit scope. Prefer one or more docket IDs with
`--docket`. Agency and year filters are also available. This milestone requires
the complete bounded selection and does not use `--textonly`.

The `--textonly` option remains available for other downloader uses, but its
restricted mirror is insufficient for Markdown structure recovery and must not
be used for this milestone.

Do not describe a filtered selection as a mirror of the entire bucket. Do not
use `--getall` for routine bounded runs.

### Initial copy and later refreshes

Use a new, empty, dedicated destination for the initial baseline. Do not point
the helper at a directory that contains generated files or files from a
differently scoped acquisition.

Let `rclone copy` provide:

- direct object copying;
- transfer concurrency;
- retries; and
- incremental retransmission.

Use `--transfers` when the default concurrency is inappropriate.

The existing helper uses `rclone copy`. This command transfers new and changed
remote objects, but it does not delete extra local files. It preserves exact
object contents, but refreshing a nonempty destination cannot, by itself,
prove that local membership exactly matches the current remote selection.

Before claiming an exact mirror after a refresh, use `rclone` to compare the
selected remote and local trees. Address all missing, differing, and extra
local files. Any future destructive use of `rclone sync` requires an explicit,
separately reviewed retention policy. Otherwise, a remote deletion could
destroy the only local copy of historical source bytes.

### Mirror verification

A successful transfer is not sufficient verification. Before downstream
processing:

1. Run `rclone check`, or an equivalent non-mutating `rclone` comparison, with
   the same selection filters.
2. Require zero missing or differing selected objects.
3. Require zero unexpected files in the dedicated mirror.
4. Keep logs such as `rclone.log` outside the mirror.

Record the following in the run manifest:

- exact selection arguments;
- remote name;
- verification command;
- verification time; and
- verification result.

Preserve downloaded `raw-data/` and `derived-data/` agency and docket paths,
including extraction-tool directories, exactly as written by `rclone`. The
enrichment pipeline receives the verified mirror as a read-only input root. It
must fail rather than relocate or modify a source file.

### Inventory and failure conditions

After verification, inventory local records and attachments as separate source
assets linked to their parent records. Do not concatenate assets without
attribution.

Record the following for every source asset:

- relative bucket key;
- size;
- SHA-256 hash; and
- locally available modification metadata.

Do not assume an S3 ETag is available or that it is a content hash. Inventory
files describe the mirror, but they must live outside it.

Identify missing expected text, incomplete docket selections, and records that
contain metadata only. Do not repair these conditions by changing the mirror.

Any of the following makes the source baseline unverified and blocks downstream
processing for the requested scope:

- a failed transfer;
- failed verification;
- a missing selected object;
- a differing object; or
- an unexpected local file.

## Stage 1: conversion to Markdown

### Source selection

Prefer available text representations over parsing binaries. For each logical
asset, choose the richest reliable representation in this order:

1. structured HTML, when present;
2. inline text or HTML from JSON; and
3. pre-extracted text.

Apply this ordering separately to each asset. A comment body and each of its
attachments remain separate. Preserve alternative extraction outputs, and
record both the selection policy and the selected extractor.

### Markdown conversion

Convert identifiable headings, paragraphs, ordered and unordered lists,
quotations, and simple tables to Markdown. Preserve source hyperlinks and
distinguish them from generated links. Escape source text where necessary to
prevent accidental Markdown syntax.

Use conservative layout heuristics for plain extracted text. Do not invent
headings or interpret every hard line break as a paragraph. Record uncertain
segmentation. Preserve complex tables conservatively and flag any lost
structure.

### Document and block metadata

Each document has front matter containing:

- document ID;
- source version and hash;
- parent record;
- docket ID;
- document type, when supplied; and
- selected source path.

Each block has an explicit anchor, such as `<a id="p-0007"></a>`. Blocks may
represent headings, list items, paragraphs, table cells where practical, and
footnotes. IDs are stable within an immutable source version. They do not need
to survive substantive source changes.

The `blocks.jsonl` file stores:

- block ID, type, and order;
- plain text;
- heading context; and
- source location.

Use HTML or XML paths and JSON field paths where available. Otherwise, use
character offsets into an identified extracted-text file. Do not claim PDF page
coordinates when the selected extraction does not provide them.

Citation offsets are Unicode code-point offsets into the block's plain text.
The end offset is exclusive.

### Deferred text transformation

Provide a future text-transform interface that initially performs an identity
transform. Defer OCR repair, spelling correction, dehyphenation, and editorial
rewriting.

Formatting normalization must record a mapping to the original representation.
Any later text correction must create a versioned derivative and retain the
original.

## Stage 2: modular citation mining

Implement adapters for:

- eyecite;
- unitedstates/citation; and
- LexNLP.

A Python orchestrator may invoke the JavaScript adapter through a Node
subprocess using JSON input and output. Keep library-specific objects and
offsets inside adapters.

Proposed common contract:

```text
adapter.capabilities() -> supported citation families and contextual features
adapter.extract(block, document_context) -> list[CitationCandidate]
```

Every enabled adapter receives the same unlinked block text. Document context
includes:

- ordered neighboring blocks;
- headings;
- document metadata; and
- prior references for short-form resolution.

When a library requires document-wide processing, map its results back to
blocks and explicitly mark boundary-spanning findings. Normalize JavaScript
UTF-16 indices to the common code-point offset convention.

Each citation candidate contains:

- schema version;
- document, version, and block IDs;
- start and end offsets;
- matched text;
- citation family;
- structured components;
- adapter name and version;
- run ID;
- optional library score; and
- warnings.

Citation families include USC, CFR, cases, public laws, Statutes at Large,
Federal Register, other authorities, and unknown. Do not presume that every
adapter supports every family. Record unsupported families and extraction
failures separately from a successful extraction with zero findings.

Retain all raw adapter findings. Failure in one adapter must not discard
successful results from another, but the overall run must report partial
completion. Pin dependencies and versions during implementation, and verify
installation compatibility for each adapter.

## Stage 3: reconciliation and target resolution

### Reconciliation

Normalize structured references into provider-independent IDs, such as
`usc:5:553:c`. Preserve original wording, pinpoint references, ranges, and
alternatives.

Merge findings that identify the same occurrence and target, while retaining
all supporting adapters. Adapter agreement is evidence of agreement, not a
calibrated accuracy probability.

Retain competing interpretations for overlapping findings. Do not arbitrarily
select an ambiguous target or nest Markdown links. Ranges and references to
multiple provisions may have multiple targets in the annotation record and a
separate Markdown reference note.

Resolve short forms, such as `Id.` and bare section numbers, only when context
supports a target. Preserve unresolved findings without linking them to an
invented authority. Distinguish proposed provisions from existing codified
provisions, even when their section numbers coincide.

### Resolver interface

Resolver interface:

```text
resolver.resolve(normalized_citation, document_context) -> Resolution
```

Preferred destinations:

| Family | Preferred destination | Fallback when a specific target is resolved |
|---|---|---|
| U.S. Code | Cornell LII `/uscode/text/<title>/<section>` | Official U.S. Code or GovInfo |
| CFR | Cornell LII `/cfr/text/<title>/<section>` | eCFR or dated GovInfo CFR |
| Cases | Cornell LII when the specific opinion is located | CourtListener or an official court/GovInfo opinion |
| Federal Register | Cornell LII if a specific matching resource exists | FederalRegister.gov or GovInfo |
| Public laws / Statutes at Large | Cornell LII if a specific matching resource exists | GovInfo |
| Other authorities | Cornell LII if resolvable | Specific official publisher page |

Do not fabricate Cornell case URLs or promise Cornell coverage for every
authority. Verify targets by identity, not merely by HTTP success. Cache
lookups and respect provider limits.

A section-level link is acceptable when a subsection anchor cannot be
verified, but record the reduced link precision. If search-result URLs are
offered for unresolved citations, label them as search aids rather than
resolved targets.

Resolution records include:

- canonical target ID;
- destination URL and provider;
- resolution status;
- link precision;
- verification status and time;
- cited date, when explicit; and
- historical-version status.

Keep `target_resolved` separate from `url_verified`. Offline rendering may use
a known URL convention while marking verification as pending. Current browsing
URLs do not establish historical text. Defer historical resolution unless an
explicit dated target is available.

## Stage 4: enriched Markdown

Generate enriched Markdown from the normalized document and reconciled
annotation records. Never mine the generated Markdown or overwrite original
source files.

Example:

```markdown
<a id="p-0007"></a>

The agency acted under [5 U.S.C. § 553](https://www.law.cornell.edu/uscode/text/5/553).
```

Preserve original citation wording and offsets in annotation sidecars. Visible
Stage 2 link text uses the current friendly reference name, initially populated
from the fetched official page title or normalized citation fallback. Existing
citation hyperlinks may be retained, with a preferred resolved URL recorded
separately.

Leave ambiguous citations as plain text and record their status in the
sidecar. Annotation records are authoritative for relationship metadata;
Markdown is the readable projection.

Assign each citation occurrence a deterministic annotation ID based on:

- document version;
- block;
- span; and
- normalized target.

Give unresolved alternatives stable occurrence IDs. Every generated link must
map to an annotation record. Rendering must be deterministic and repeatable,
with no duplicate links after reruns.

## Operations and acceptance criteria

### Command-line stages and configuration

Run acquisition separately with
`scripts/rclone/mirrulations_downloader.py`. Acquisition is not an enrichment
CLI stage.

The proposed enrichment CLI stages are:

- `verify`;
- `inventory`;
- `convert`;
- `mine`;
- `resolve`;
- `render`; and
- `run`.

These are design names, not replacement download commands.

For the approved milestone, the user-facing workflow may expose the clearer
names `verify`, `inventory`, `initial-markdown`, `add-citations`, and `run`.
`add-citations` encompasses the internal mining, reconciliation, resolution,
and rendering operations. Acquisition remains a separate invocation of
`scripts/rclone/mirrulations_downloader.py`; the enrichment application must
not introduce another downloader.

The `run` operation begins with verification and inventory, then creates Stage
1 and Stage 2 in order. It must refuse an unverified source mirror. Targeted
commands may rerun one operation when its prerequisites have valid manifests.

Configuration selects:

- the dedicated `rclone` mirror as the read-only input root;
- the exact acquisition scope;
- source preferences;
- enabled adapters;
- resolver policy; and
- a separate output root.

The output root must not be inside the source mirror. For each run, persist:

- the effective configuration;
- `rclone` selection and verification details;
- the source inventory with hashes; and
- dependency versions.

### Runtime behavior and reporting

Refuse to process an unverified mirror. Once verified, cache each stage by the
source SHA-256 and the relevant configuration and tool versions. Changed source
bytes invalidate dependent outputs and create a distinct source version.

Before reporting processing counts, report mirror verification status and
counts for:

- expected objects;
- matching objects;
- missing objects;
- differing objects; and
- unexpected objects.

Keep transfer logs outside the mirror. Clearly distinguish `rclone` transfer
results from enrichment results.

Continue processing independent assets after recoverable failures. Return a
non-success status when requested work is incomplete, and permit targeted
reruns. Treat source content, including embedded markup, as data. Never execute
or modify it.

### Initial acceptance criteria

1. The selected bounded scope is copied with the existing `rclone` helper into
   a clean, dedicated, ignored source-mirror path. No application-specific
   downloader is used. Original files are included as structural evidence.
2. An `rclone` comparison confirms that every selected object has the same
   bytes and relative path as Mirrulations and that the dedicated mirror
   contains no unexpected files. Downstream stages refuse an unverified mirror.
3. Non-JSON source files remain unchanged after a complete run. JSON is
   pretty-printed only after successful verification, with original and local
   hashes recorded. Other generated artifacts remain outside the source tree.
4. Every derivative records the relative Mirrulations object key and SHA-256
   of its exact source bytes. A changed remote object creates a new source
   version rather than silently replacing prior provenance.
5. Comment bodies, agency documents, and attachments retain separate identities
   and provenance.
6. Fixtures preserve paragraphs, headings, lists, existing links, and citation
   wording in readable Markdown.
7. All three adapters implement the same contract, preserve Unicode-correct
   spans, and report failures independently.
8. Duplicate findings merge without losing provenance. Overlaps, ranges,
   ambiguous references, and unsupported formats remain inspectable.
9. Resolved USC and CFR references use Cornell where possible. Unavailable
   Cornell targets use specific fallback resources or remain unresolved.
10. Every generated link has an annotation record and source location. Reruns
    reproduce outputs without duplicate enrichment.
11. No OCR repair, LLM inference, historical reconstruction, or Neo4j
    implementation is silently included in this increment.
12. Initial Markdown is written only beneath
    `stage001_initial_markdown_mirror/`, and citation-enriched Markdown is
    written only beneath `stage002_addition_of_citations/` under the configured
    Markdown database root.
13. The Markdown database root defaults to `./data/markdown_db/`, respects
    `MARKDOWN_DB_PATH`, and is validated as non-overlapping with the source
    mirror.
14. Stage 2 is generated from Stage 1 plus authoritative annotation sidecars;
    it does not modify Stage 1 or mine previously generated Stage 2 Markdown.
15. A repeated run with identical source bytes, configuration, and tool
    versions produces stable paths, block IDs, annotation IDs, and Markdown
    without duplicate links.

## Extension boundary: Neo4j and later passes

The future importer reads document and block manifests plus annotation sidecars.
It does not reconstruct meaning from bare URLs.

The initial graph shape is:

```text
DocumentVersion -HAS_BLOCK-> Block -CITES-> Authority
```

Citation-occurrence nodes preserve spans and provenance. Keep current authority
identity separate from any later authority-version nodes. Graph data must be
rebuildable from files.

Later enrichers reuse the same annotation envelope for:

- document references;
- arguments;
- inferred responses;
- dispositions; and
- topical relationships.

They append annotations and regenerate Markdown without modifying source
wording. Explicit citations and inferred relationships remain separately typed.

## Reference documentation

- [Mirrulations AWS registry](https://registry.opendata.aws/mirrulations/)
- [Mirrulations directory structure](https://github.com/MoravianUniversity/mirrulations-data/blob/main/structure.md)
- [eyecite](https://github.com/freelawproject/eyecite)
- [unitedstates/citation](https://github.com/unitedstates/citation)
- [LexNLP regulatory extraction](https://publicdocs.contraxsuite.com/lexnlp/modules/extract/en/regulations.html)
- [Cornell LII example: 5 USC 553](https://www.law.cornell.edu/uscode/text/5/553)
- [GovInfo](https://www.govinfo.gov/)
