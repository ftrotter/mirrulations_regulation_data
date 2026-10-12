# Mirrulations S3 and On-Disk Data Structure

This is a corrected local edition of the current upstream Mirrulations data
structure documentation. It describes how Regulations.gov resources and
Mirrulations-derived artifacts are stored on disk and in the public
`s3://mirrulations/` bucket.

## Provenance of this edition

This edition was prepared from:

- [`mirrulations/mirrulations/docs/structure.md`](https://github.com/mirrulations/mirrulations/blob/main/docs/structure.md)
  at commit `9442a69de02b39588b5c15fd8c2656f27a8b99fc`;
- the upstream `PathGenerator`, `DiskSaver`, client documentation, and tests at
  that commit;
- the older
  [`mirrulations-data/structure.md`](https://github.com/MoravianUniversity/mirrulations-data/blob/main/structure.md);
  and
- the locally mirrored docket `CMS-2026-1255`.

The exact downloaded upstream Markdown is preserved locally as
[`MirrulationsStructureUpstream.md`](MirrulationsStructureUpstream.md). Its
SHA-256 is:

```text
5599ca5becb78697396e26a7236d009d5e0cd4458cef826c5b79613c94f69980
```

Corrections and clarifications in this edition include:

- explicit disk versus S3 path notation;
- unambiguous derived-data namespace nesting;
- both `.htm` and `.html` document-body names;
- exact JSON revision behavior;
- exact tombstone content and naming;
- optional-directory semantics;
- arbitrary attachment formats;
- `unknown` path fallbacks;
- a clearer separation between raw and derived authority.

## Data categories

The Regulations.gov API provides several kinds of **raw data**:

- **Docket metadata**: JSON describing a docket.
- **Document metadata**: JSON describing a regulatory document.
- **Document body**: an HTM or HTML representation of a document when
  Regulations.gov provides one.
- **Comment metadata**: JSON describing a public submission and potentially
  containing comment text entered into the web form.
- **Comment attachments**: files attached to a public submission. Formats are
  not limited to PDF and DOCX, although those formats are common.

Mirrulations also stores **derived data**. Derived data is generated from one or
more raw files. A typical example is text extracted from a PDF comment
attachment with `pypdf`.

Raw and derived files are intentionally separated so users can:

- distinguish mirrored source from generated output;
- preserve every raw version;
- retain links between metadata, attachments, and extractions;
- identify who generated derived data and for which project;
- add new derived products without changing raw data;
- record unavailable resources explicitly.

## Root paths

The S3 root is:

```text
s3://mirrulations/
```

The client uses equivalent saver-relative paths beginning with `/raw-data/`.
When written to local disk in the standard container setup, these paths are
rooted beneath the mounted data directory. The logical hierarchy is the same on
disk and in S3.

## Complete logical structure

```text
s3://mirrulations/
├── raw-data/
│   └── <agency>/
│       └── <docket-id>/
│           ├── text-<docket-id>/
│           │   ├── comments/
│           │   │   ├── <comment-id>.json
│           │   │   ├── <comment-id>(1).json
│           │   │   ├── <comment-id>_UNAVAILABLE
│           │   │   └── ...
│           │   ├── docket/
│           │   │   ├── <docket-id>.json
│           │   │   ├── <docket-id>(1).json
│           │   │   ├── <docket-id>_UNAVAILABLE
│           │   │   └── ...
│           │   └── documents/
│           │       ├── <document-id>.json
│           │       ├── <document-id>(1).json
│           │       ├── <document-id>_content.htm
│           │       ├── <document-id>_content.html
│           │       ├── <document-id>_UNAVAILABLE
│           │       ├── <document-id>_content_UNAVAILABLE
│           │       └── ...
│           └── binary-<docket-id>/
│               └── comments_attachments/
│                   ├── <comment-id>_attachment_<counter>.<extension>
│                   ├── <comment-id>_attachment_<counter>_UNAVAILABLE
│                   └── ...
└── derived-data/
    └── <agency>/
        └── <docket-id>/
            └── <organization>/
                └── <project-name>/
                    └── <file-type>/
                        └── <project-defined-data-path>
```

Not every docket has every directory. Empty attachment or derived-data branches
can be absent.

## Raw-data structure

Raw paths encode:

```text
agency → docket ID → text or binary branch → resource kind → resource identity
```

### Agency and docket

The first two path components identify the agency and docket:

```text
raw-data/<agency>/<docket-id>/
```

Examples:

```text
raw-data/CMS/CMS-2026-1255/
raw-data/HUD/HUD-2026-0529/
```

### Text branch

Text-oriented API results are stored beneath:

```text
raw-data/<agency>/<docket-id>/text-<docket-id>/
```

This branch contains JSON metadata and readable document bodies. "Text" does
not mean every file is prose; JSON files are structured metadata.

### Binary branch

Downloaded comment attachments are stored beneath:

```text
raw-data/<agency>/<docket-id>/binary-<docket-id>/comments_attachments/
```

The current client obtains the attachment filename tail from the Regulations.gov
`fileUrl` and prefixes it with the public comment ID:

```text
<comment-id>_<fileUrl-basename>
```

For standard Regulations.gov attachment URLs, this yields:

```text
<comment-id>_attachment_<counter>.<extension>
```

Examples:

```text
CMS-2026-1255-0032_attachment_1.pdf
CMS-2026-1255-0002_attachment_1.docx
```

The format is arbitrary. A docket can contain PDF, DOCX, PNG, TXT, spreadsheet,
archive, or other public attachment types.

## Resource filenames

### Docket metadata

Canonical path:

```text
raw-data/<agency>/<docket-id>/text-<docket-id>/docket/<docket-id>.json
```

Example:

```text
raw-data/CMS/CMS-2026-1255/text-CMS-2026-1255/docket/
CMS-2026-1255.json
```

### Document metadata

Canonical path:

```text
raw-data/<agency>/<docket-id>/text-<docket-id>/documents/<document-id>.json
```

### Document body

Depending on the format advertised by Regulations.gov, the client uses:

```text
<document-id>_content.htm
```

or:

```text
<document-id>_content.html
```

The body is stored beside document metadata in the `documents/` directory.

### Comment metadata

Canonical path:

```text
raw-data/<agency>/<docket-id>/text-<docket-id>/comments/<comment-id>.json
```

The JSON can include comment text submitted through the Regulations.gov form as
well as attachment metadata and links.

## JSON revisions

Mirrulations preserves changed JSON payloads rather than overwriting the
canonical file.

The disk saver behaves as follows:

1. If `<id>.json` does not exist, write it.
2. If the new payload equals the existing canonical payload, do not write a
   duplicate.
3. If the payload differs, try `<id>(1).json`.
4. If that file exists with equal content, stop.
5. Otherwise continue with `<id>(2).json`, `<id>(3).json`, and so on.

Therefore:

```text
<id>.json
<id>(1).json
<id>(2).json
```

represent distinct observed payload versions, not independent Regulations.gov
resources. The embedded `data.id` normally remains the same.

Revision suffixes are currently applied to JSON persistence. Binary saving uses
the canonical path and does not use this JSON revision algorithm.

## Unavailable-resource tombstones

When a requested primary resource, attachment, or document body returns a
non-success HTTP response, Mirrulations writes an extensionless tombstone.

Naming removes the expected extension and appends:

```text
_UNAVAILABLE
```

Examples:

```text
<comment-id>_UNAVAILABLE
<document-id>_UNAVAILABLE
<document-id>_content_UNAVAILABLE
<comment-id>_attachment_1_UNAVAILABLE
```

The tombstone body is exactly one UTF-8 line:

```text
HTTP <status-code>
```

For example:

```text
HTTP 404
```

A tombstone records a failed fetch at a point in time. It is not a successful
empty resource and should not be parsed as JSON or attachment content.

## Missing identifiers and `unknown`

The current path generator falls back to `unknown` when agency, docket, or item
identity needed for a path is missing. For non-docket resources, it can derive a
docket ID by dropping the last hyphen-separated segment of the item ID.

Paths containing `unknown` should be treated as degraded-provenance records and
reviewed rather than silently joined to a normal docket.

## Derived-data structure

Derived data starts with the same agency and docket identity as its raw inputs:

```text
derived-data/<agency>/<docket-id>/
```

Below the docket, it is namespaced by:

```text
<organization>/<project-name>/<file-type>/
```

Organizations have flexibility below that namespace. Every derived-data project
should nevertheless make its source relationship, method, and version clear.

A current Mirrulations text-extraction project uses:

```text
derived-data/<agency>/<docket-id>/mirrulations/extracted_txt/
└── comments_extracted_text/
    └── pypdf/
        └── <comment-id>_attachment_<counter>_extracted.txt
```

Example:

```text
derived-data/CMS/CMS-2026-1255/mirrulations/extracted_txt/
comments_extracted_text/pypdf/
CMS-2026-1255-0032_attachment_1_extracted.txt
```

The source relationship is:

```text
raw-data/.../comments_attachments/
<comment-id>_attachment_<counter>.pdf
    ↓ text extraction with pypdf
derived-data/.../comments_extracted_text/pypdf/
<comment-id>_attachment_<counter>_extracted.txt
```

Derived text is not a byte-exact copy of the PDF and does not replace the raw
attachment. It is a generated representation whose extraction method is part
of its provenance.

## Example docket

The following concise example reflects the current layout:

```text
s3://mirrulations/
├── raw-data/
│   └── HUD/
│       └── HUD-2026-0529/
│           ├── text-HUD-2026-0529/
│           │   ├── docket/
│           │   │   ├── HUD-2026-0529.json
│           │   │   └── HUD-2026-0529(1).json
│           │   ├── documents/
│           │   │   ├── HUD-2026-0529-0001.json
│           │   │   └── HUD-2026-0529-0001_content.html
│           │   └── comments/
│           │       ├── HUD-2026-0529-0002.json
│           │       └── HUD-2026-0529-0099_UNAVAILABLE
│           └── binary-HUD-2026-0529/
│               └── comments_attachments/
│                   ├── HUD-2026-0529-0011_attachment_1.pdf
│                   └── HUD-2026-0529-0404_attachment_1_UNAVAILABLE
└── derived-data/
    └── HUD/
        └── HUD-2026-0529/
            └── mirrulations/
                └── extracted_txt/
                    └── comments_extracted_text/
                        └── pypdf/
                            └── HUD-2026-0529-0011_attachment_1_extracted.txt
```

## File linkage rules

The path layout maintains several important links:

| From | To | Link key |
|---|---|---|
| Docket JSON | Documents and comments | Docket ID |
| Document JSON | Document body | Document ID |
| Comment JSON | Comment attachment | Comment ID plus attachment filename/ordinal |
| Raw attachment | Derived extraction | Comment ID plus attachment ordinal |
| JSON revision | Canonical resource | Same path stem and embedded `data.id` |
| Tombstone | Attempted resource | Canonical stem plus `_UNAVAILABLE` |

Always use complete object keys and content hashes when provenance matters.
Basenames alone are not globally unique across agencies, dockets, and versions.

## Raw versus derived authority

- Raw JSON is the mirrored Regulations.gov API payload for that observed
  version.
- Raw HTML is the downloaded document body.
- Raw attachments are the downloaded public files.
- Derived files are generated analyses or representations.
- Revision files preserve changed API payloads.
- Tombstones preserve failed retrieval outcomes.

Do not modify raw data to repair extraction or normalization problems. Produce a
new derived artifact with explicit provenance instead.

## Optional and project-specific paths

The canonical current client explicitly writes:

- docket JSON;
- document JSON;
- document HTM/HTML bodies;
- comment JSON;
- comment attachments;
- tombstones for unsuccessful retrievals.

The generic derived-data namespace supports many future products. Paths such as
`documents_extracted_text` or raw document-attachment directories can exist in
historical datasets or separate projects, but they are not required products of
the current client path generator shown in this source version.

Do not create empty directories merely to match a diagram. Object storage does
not require directory objects, and local directories are created when files are
written.

## Relationship to this repository

This repository treats the Mirrulations mirror as immutable input. It inventories
raw and derived objects, pairs extracted comment text with raw attachments, and
writes a separate Markdown database.

For source-resource and regulatory-phase relationships, see
[`MirrulationsRegulatoryDocumentStructure.md`](MirrulationsRegulatoryDocumentStructure.md).
For the downstream semantic Markdown and metadata contracts, see
[`RichDocumentStructure.md`](RichDocumentStructure.md).

## Known upstream documentation corrections

The downloaded upstream document is substantially current and matches the
observed mirror. This corrected edition addresses these remaining issues:

1. The generic derived-data tree can visually imply that `project-name` and
   `file-type` are siblings. They are nested:
   `<organization>/<project-name>/<file-type>`.
2. It shows `_content.html` but the implementation supports both `.htm` and
   `.html`.
3. It describes tombstone files but does not state their exact body,
   `HTTP <status-code>`.
4. It does not explain that equal JSON payloads are deduplicated while changed
   payloads receive the next revision suffix.
5. It does not mention the `unknown` fallback used when path identity is
   incomplete.
6. Related client documentation links to “Tombstone files” and “Unparseable API
   responses” subsections that are not present as headings in the downloaded
   `structure.md`.
7. The raw-data diagram can be read as requiring every directory for every
   docket; these branches are optional and appear only when corresponding files
   exist.

The older `mirrulations-data/structure.md` is historical and should not be used
as the current layout authority. It predates the raw/derived split, revision
files, tombstones, and namespaced derived-data structure.