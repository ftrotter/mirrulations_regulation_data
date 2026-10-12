# Mirrulations Regulatory Document Structure

This document explains the source data mirrored from Regulations.gov and the
relationships among Mirrulations raw data, Mirrulations derived data, public
comments, attachments, regulatory documents, dockets, and phases of the
regulatory process.

For the progressively enriched Markdown database built by this repository, see
[`RichDocumentStructure.md`](RichDocumentStructure.md).

For the evidence-based comparison of Regulations.gov metadata across 28
regulatory and Privacy Act artifact categories, see
[`RegulationsGovRegulatoryProcessMetadata.md`](RegulationsGovRegulatoryProcessMetadata.md).

The most important distinctions are:

> **Regulations.gov resources describe regulatory records and relationships.
> Mirrulations preserves those records and files in a browsable mirror.
> Mirrulations derived data contains generated representations of raw files.
> This repository's Markdown database is a separate downstream analytical
> product.**

Do not treat a generated text extraction as the original attachment. Do not
treat a docket as one document. Do not treat every record in a docket as one
phase or one version of the same regulatory text.

## Sources and scope

This guide is based on:

- the current upstream
  [Mirrulations S3 structure documentation](https://github.com/mirrulations/mirrulations/blob/main/docs/structure.md);
- the corrected local edition,
  [`MirrulationsStructureCorrected.md`](MirrulationsStructureCorrected.md), and
  exact downloaded upstream copy,
  [`MirrulationsStructureUpstream.md`](MirrulationsStructureUpstream.md);
- the older, historical
  [`mirrulations-data/structure.md`](https://github.com/MoravianUniversity/mirrulations-data/blob/main/structure.md);
- the official
  [Regulations.gov API documentation](https://open.gsa.gov/api/regulationsgov/);
- the Regulations.gov v4 records mirrored in this repository's selected
  Mirrulations source tree;
- the observed Mirrulations path conventions for docket
  `CMS-2026-1255`; and
- the pairing and document-selection code in this repository.

The official API documentation describes API resource semantics. Directory
names such as `text-<docket>`, `binary-<docket>`, and
`comments_extracted_text/pypdf` are Mirrulations storage conventions, not
Regulations.gov API guarantees.

The current `mirrulations/mirrulations` structure document is the upstream
authority for the intended S3 and on-disk layout. This guide does not replace
it. It explains Regulations.gov resource relationships and this repository's
downstream use of the mirror. The local corrected edition records clarifications
and small corrections without altering the verbatim downloaded copy.

The official OpenAPI file rejected automated retrieval during preparation of
this guide. Field examples below were therefore checked against both the
official rendered API documentation and actual mirrored v4 detail records.

## Four layers of data

It is useful to reason about four distinct layers:

1. **Regulations.gov API resources**
   - dockets;
   - documents;
   - comments;
   - attachments.
2. **Mirrulations raw data**
   - mirrored JSON metadata;
   - mirrored HTML or text content;
   - mirrored original PDF, DOCX, image, or other binary files.
3. **Mirrulations derived data**
   - generated text extraction from an original binary asset;
   - extraction-method-specific output, such as `pypdf` text.
4. **This repository's Markdown database**
   - selected readable logical documents;
   - semantic blocks;
   - citation enrichment;
   - backward-reference discovery and exact links.

Each layer has different authority:

- Regulations.gov fields are authoritative for public API record metadata.
- A Mirrulations raw binary is the authoritative mirrored attachment file.
- Derived extraction is authoritative only as a record of what that extraction
  process produced.
- The Markdown database's metadata sidecars are authoritative for this
  repository's semantic blocks and analytical enrichments.

## Regulations.gov JSON:API envelope

Regulations.gov v4 uses a JSON:API-style resource envelope. A detail response
typically contains:

```json
{
  "data": {
    "id": "RESOURCE-ID",
    "type": "comments",
    "attributes": {},
    "relationships": {},
    "links": {
      "self": "https://api.regulations.gov/v4/comments/RESOURCE-ID"
    }
  },
  "included": []
}
```

Important envelope concepts are:

- `data`: the primary resource;
- `data.id`: the public Regulations.gov resource ID;
- `data.type`: the resource collection, such as `comments`, `documents`, or
  `dockets`;
- `data.attributes`: resource-specific values;
- `data.relationships`: links to related resources;
- `data.links.self`: the API URL for the resource;
- `included`: related resources embedded in the response, often attachments.

Search/list responses can use an array in `data` and include pagination and
top-level links. Detail records mirrored here generally contain one object in
`data`.

Null fields are common and meaningful. Code should tolerate absent, `null`, or
agency-specific fields rather than assuming every resource has the same
populated attributes.

## Historical versus current Mirrulations documentation

The older `mirrulations-data/structure.md` specifies this historical conceptual
per-docket layout:

```text
data/
└── <agency>/
    └── <docket-id>/
        ├── binary-<docket-id>/
        │   ├── comments_attachments/
        │   └── documents_attachments/
        └── text-<docket-id>/
            ├── comments/
            ├── comments_extracted_text/<tool-name>/
            ├── docket/
            ├── documents/
            └── documents_extracted_text/<tool-name>/
```

The current
[`mirrulations/mirrulations/docs/structure.md`](https://github.com/mirrulations/mirrulations/blob/main/docs/structure.md)
supersedes that layout. It documents the modern `raw-data` / `derived-data`
split, revision files, unavailable-resource tombstones, and derived-data
namespaces. See [`MirrulationsStructureCorrected.md`](MirrulationsStructureCorrected.md)
for a concise corrected edition.

The durable rules shared by both generations are:

- organize resources by agency and docket;
- separate binary attachments from text-oriented data;
- name comment JSON and attachments with the public comment ID;
- name document JSON and content with the public document ID;
- separate extraction results by extraction tool;
- retain attachment ordinals in comment extraction filenames.

## Current Mirrulations mirror layout

The current upstream documentation and local mirror use:

```text
data/source/mirrulations/
├── raw-data/
│   └── <agency>/
│       └── <docket-id>/
│           ├── text-<docket-id>/
│           │   ├── comments/
│           │   │   └── <comment-id>.json
│           │   ├── documents/
│           │   │   ├── <document-id>.json
│           │   │   └── <document-id>_content.html
│           │   └── docket/
│           │       └── <docket-id>.json
│           └── binary-<docket-id>/
│               └── comments_attachments/
│                   ├── <comment-id>_attachment_1.pdf
│                   └── <comment-id>_attachment_1.docx
└── derived-data/
    └── <agency>/
        └── <docket-id>/
            └── mirrulations/
                └── extracted_txt/
                    └── comments_extracted_text/
                        └── pypdf/
                            └── <comment-id>_attachment_1_extracted.txt
```

For the current docket, substitutions include:

```text
<agency> = CMS
<docket-id> = CMS-2026-1255
```

The exact set of subdirectories and derived extraction methods can vary by
docket and Mirrulations processing history.

### Historical documentation versus current mirror

| Concern | Historical `mirrulations-data` document | Current documentation and `CMS-2026-1255` mirror |
|---|---|---|
| Top-level provenance | One `data/<agency>/<docket>` tree | Separate `raw-data/` and `derived-data/` trees |
| JSON and original files | `text-*` and `binary-*` below the docket | Same branches below `raw-data/<agency>/<docket>` |
| Extracted comment text | `text-*/comments_extracted_text/<tool>` | `derived-data/.../mirrulations/extracted_txt/comments_extracted_text/<tool>` |
| Extracted document text | `text-*/documents_extracted_text/<tool>` | Not present in this docket; document HTML is available |
| Document attachments | `binary-*/documents_attachments` in the tree example | Not present in this docket |
| Extraction tool | Example uses `pikepdf` | Current docket uses `pypdf` |
| Resource JSON copies | Describes one JSON per resource | Some mirrored names have collision suffixes such as `(1)` |

The current mirror contains 722 comment JSON files, 17 document JSON files,
five docket JSON files, 425 PDF comment attachments, 40 DOCX comment
attachments, and 412 `pypdf` comment extractions. It also contains several PNG
and plain-text attachments. These counts describe this local bounded mirror,
not the canonical format or all Mirrulations dockets.

### Does the current upstream documentation need correction?

The current software-repository document is substantially accurate and matches
the local mirror. The major discrepancy was that the previously consulted
`mirrulations-data` document was historical, not that the mirror violated the
current specification.

The current upstream document could still be improved to:

1. make the generic derived-data nesting visually unambiguous;
2. document both `.htm` and `.html` document-body paths;
3. state the exact `HTTP <status-code>` tombstone body;
4. explain content-sensitive JSON revision and deduplication behavior;
5. mention `unknown` path fallbacks;
6. add the missing tombstone and unparseable-response headings referenced by
   `client.md`; and
7. clarify that path branches are optional when no corresponding files exist.

Those corrections are incorporated in
[`MirrulationsStructureCorrected.md`](MirrulationsStructureCorrected.md).

## Raw text data

The raw `text-<docket-id>` branch contains text-oriented material obtained from
Regulations.gov. In this docket it contains:

- comment detail JSON under `comments/`;
- regulatory-document detail JSON and content HTML under `documents/`;
- docket detail JSON under `docket/`.

"Text" in this path name does not mean every file is natural-language body
text. Many files are metadata-only JSON resources.

### Comment JSON as body text

Some comment JSON records contain substantive text in:

```text
data.attributes.comment
```

When that field is a nonempty string, this repository can select the JSON itself
as a readable logical document with:

```text
selection_reason = form-submitted-comment-body
content_location = data.attributes.comment
```

The full JSON remains metadata and provenance. Only the public comment-body
field becomes source content in the Markdown projection.

### Attachment-placeholder comments

A comment body can be only a placeholder such as:

```text
See attached
```

If an actual attachment exists, that placeholder is not the substantive comment
letter. This repository preserves the form body and attachment extraction as
separate document identities, while Stage 3 eligibility can exclude the short
placeholder from AI analysis.

### Regulatory-document content

A document JSON record can advertise downloadable content in
`attributes.fileFormats`, while Mirrulations separately stores readable content
such as:

```text
<document-id>_content.html
```

The document JSON is metadata. The content HTML is the substantive regulatory
text selected for semantic block creation.

## Raw binary data

The raw `binary-<docket-id>` branch contains original downloaded files, such as:

- PDF comment attachments;
- DOCX comment attachments;
- images or other supported attachment formats.

Example:

```text
raw-data/CMS/CMS-2026-1255/
binary-CMS-2026-1255/comments_attachments/
CMS-2026-1255-0032_attachment_1.pdf
```

These files provide original layout and structural evidence. They are not
rewritten into Markdown in place.

The public comment ID and attachment ordinal are encoded in the mirrored
filename. The API's attachment resource itself has a separate opaque ID, such
as `09000064b92ed088`.

## Mirrulations derived data

The `derived-data` tree contains generated artifacts produced from raw source
files. For example:

```text
derived-data/CMS/CMS-2026-1255/mirrulations/
extracted_txt/comments_extracted_text/pypdf/
CMS-2026-1255-0032_attachment_1_extracted.txt
```

This path conveys several facts:

- the data is derived rather than directly mirrored source content;
- it is a text extraction;
- it came from a comment attachment;
- the extraction method is `pypdf`;
- its logical parent is comment `CMS-2026-1255-0032`, attachment 1.

### Derived data is not a duplicate raw document

The extraction and original binary represent different aspects of one logical
attachment:

```text
original PDF/DOCX
    ├── authoritative downloaded bytes and layout
    └── structural source for headings, lists, pages, and tables

derived extracted TXT
    ├── canonical machine-readable text representation
    └── input for text alignment and semantic-block generation
```

Do not count the PDF, DOCX, and extracted TXT as three independent public
comments. They can be multiple representations of one attachment.

At the same time, do not discard their separate provenance. An extraction can
contain errors not present in the original, while a PDF and DOCX may preserve
different structural signals.

## Pairing derived extraction with an original attachment

This repository recognizes extracted attachment names matching:

```text
<record-id>_attachment_<number>_extracted.txt
```

It pairs them with structural source names matching:

```text
<record-id>_attachment_<number>.<suffix>
```

The identity tuple is:

```text
(record_id, attachment_number)
```

Current structural suffixes include:

- `.pdf`;
- `.docx`;
- `.png`;
- `.jpg`;
- `.jpeg`.

When exactly one DOCX and one PDF are available, the repository prefers DOCX
for structural recovery and retains the PDF as an alternate structural source.
When no unique DOCX exists, it uses a unique PDF. Ambiguity and missing-original
states are recorded rather than guessed.

A pairing record contains fields such as:

```json
{
  "canonical_source_object_key": "derived-data/..._extracted.txt",
  "canonical_source_sha256": "...",
  "record_id": "CMS-2026-1255-0032",
  "attachment_number": 1,
  "status": "available-pdf",
  "structural_source_object_key": "raw-data/..._attachment_1.pdf",
  "structural_source_sha256": "...",
  "structural_source_format": "pdf",
  "alternate_structural_sources": [],
  "candidate_source_object_keys": []
}
```

"Canonical" here means the selected text representation for this Markdown
pipeline. It does not mean the extracted text supersedes the original public
attachment.

## Comment resource structure

An observed comment detail record has:

```json
{
  "data": {
    "id": "CMS-2026-1255-0032",
    "type": "comments",
    "attributes": {
      "agencyId": "CMS",
      "docketId": "CMS-2026-1255",
      "documentType": "Public Submission",
      "subtype": "Public Comment",
      "title": "Comment on CMS-2026-1255-0001",
      "comment": "See attached",
      "commentOnDocumentId": "CMS-2026-1255-0001",
      "commentOn": "09000064b927bd06",
      "organization": "American Association of Orthopaedic Surgeons",
      "postedDate": "2026-06-10T04:00:00Z",
      "receiveDate": "2026-05-22T04:00:00Z",
      "trackingNbr": "mph-2mlk-j238",
      "withdrawn": false
    },
    "relationships": {
      "attachments": {
        "data": [
          {
            "id": "09000064b92ed088",
            "type": "attachments"
          }
        ]
      }
    }
  },
  "included": []
}
```

This example is abbreviated. The actual record contains many public fields,
including nullable contact, category, restriction, duplication, page-count,
and submission metadata.

### Important comment fields

| Field | Meaning in analysis |
|---|---|
| `data.id` | Public comment/submission record ID |
| `agencyId` | Agency code |
| `docketId` | Docket container to which the comment belongs |
| `commentOnDocumentId` | Public document ID directly commented upon |
| `commentOn` | Opaque target object ID in observed records |
| `comment` | Form-submitted public comment text or placeholder |
| `documentType` | Broad record classification, commonly `Public Submission` |
| `subtype` | More specific classification, such as `Public Comment` |
| `organization` | Public submitter organization when supplied |
| `postedDate` | Date made available on Regulations.gov |
| `receiveDate` | Date received by the agency/system |
| `trackingNbr` | Submission tracking number |
| `withdrawn` | Whether the public record is withdrawn |

Fields can be agency-configurable, redacted, restricted, or null. Their public
presence does not imply completeness or verification of submitter assertions.

### Public and private comment fields

The official API documentation distinguishes:

- fields always publicly viewable;
- agency-configurable public fields; and
- fields never publicly viewable.

This mirror contains public API output, not a complete private submission
record. Absence of a field does not prove that the submitter never supplied it.

## Comment attachment structure

The comment's `relationships.attachments.data` gives attachment resource
identifiers. A detail response can also place attachment resources in
top-level `included`:

```json
{
  "id": "09000064b92ed088",
  "type": "attachments",
  "attributes": {
    "docOrder": 1,
    "title": "AAOS 2027 e-PA Comment Letter Final",
    "fileFormats": [
      {
        "fileUrl": "https://downloads.regulations.gov/CMS-2026-1255-0032/attachment_1.pdf",
        "format": "pdf",
        "size": 379443
      }
    ],
    "modifyDate": "2026-05-22T15:25:07Z"
  }
}
```

Important distinctions are:

- attachment **resource ID**: opaque API ID;
- parent **comment ID**: public Regulations.gov record ID;
- attachment **ordinal**: `docOrder` and `_attachment_<n>` filename suffix;
- attachment **formats**: one attachment resource may advertise one or more
  downloadable file formats.

The safest parent join is the comment relationship or the download URL path,
not an attempt to derive the parent comment ID from the opaque attachment ID.

## Regulatory document resource structure

An observed proposed-rule document record has:

```json
{
  "data": {
    "id": "CMS-2026-1255-0001",
    "type": "documents",
    "attributes": {
      "agencyId": "CMS",
      "docketId": "CMS-2026-1255",
      "documentType": "Proposed Rule",
      "title": "Medicare and Medicaid Programs: ...",
      "commentStartDate": "2026-04-14T04:00:00Z",
      "commentEndDate": "2026-06-16T03:59:59Z",
      "openForComment": true,
      "withinCommentPeriod": true,
      "frDocNum": "2026-07205",
      "cfrPart": "42 CFR Parts 403, 422, 431, 438, 440, and 457",
      "originalDocumentId": "CMS_FRDOC_0001-4341",
      "fileFormats": [
        {
          "format": "pdf",
          "fileUrl": "https://downloads.regulations.gov/.../content.pdf"
        },
        {
          "format": "html",
          "fileUrl": "https://downloads.regulations.gov/.../content.html"
        }
      ],
      "withdrawn": false
    }
  }
}
```

### Important document fields

| Field | Meaning in analysis |
|---|---|
| `data.id` | Public Regulations.gov document ID |
| `docketId` | Docket containing the document |
| `documentType` | Regulatory/publication type, such as `Proposed Rule` |
| `title` | Public title |
| `frDocNum` | Federal Register document number when supplied |
| `cfrPart` | CFR parts associated with the action |
| `commentStartDate` | Opening of the associated comment period |
| `commentEndDate` | Closing of the associated comment period |
| `openForComment` | Current comment-acceptance state |
| `withinCommentPeriod` | Whether the record is within the period at response time |
| `effectiveDate` | Effective date when relevant to the document phase |
| `fileFormats` | Downloadable content representations |
| `originalDocumentId` | Legacy or source-system identifier when supplied |
| `withdrawn` | Regulations.gov v4 withdrawal indicator |

The official documentation notes that `withdrawn` replaces assumptions about a
separate search-result status: `true` means withdrawn; otherwise the document
is posted.

## Docket resource structure

A docket is the regulatory container, not the proposed rule itself. An observed
docket record has:

```json
{
  "data": {
    "id": "CMS-2026-1255",
    "type": "dockets",
    "attributes": {
      "agencyId": "CMS",
      "docketType": "Rulemaking",
      "title": "Medicare and Medicaid Programs; ... (CMS-0062-P)",
      "dkAbstract": "These proposals are intended to ...",
      "rin": "0938-AV44",
      "modifyDate": "2026-05-14T13:33:42Z"
    }
  }
}
```

Important docket concepts are:

- `data.id`: docket ID used by comments and documents;
- `agencyId`: owning agency code;
- `docketType`: broad process type, such as `Rulemaking`;
- `title` and `dkAbstract`: process-level description;
- `rin`: Regulation Identifier Number when supplied.

The official documentation notes that some values formerly available in older
search APIs now require detail endpoints. For example, RIN belongs to docket
detail rather than the v4 document search result.

## Identifier taxonomy

Several IDs coexist and must not be conflated.

### Docket ID

Example:

```text
CMS-2026-1255
```

This groups public records in one Regulations.gov docket.

### Regulatory document ID

Example:

```text
CMS-2026-1255-0001
```

This identifies a particular document resource, here the proposed rule.

### Comment ID

Example:

```text
CMS-2026-1255-0032
```

This identifies a public submission/comment resource.

### Attachment resource ID

Example:

```text
09000064b92ed088
```

This is an opaque attachment resource identity. It does not have the public
docket-number form.

### Object ID

Comment and document attributes can include opaque `objectId` values. In the
observed example:

```text
comment.attributes.commentOn
    = document.attributes.objectId
```

Prefer `commentOnDocumentId` for a human-readable public-document join when it
is available.

### RIN

Example:

```text
0938-AV44
```

The Regulation Identifier Number identifies a rulemaking action in the federal
regulatory agenda system. It is not a Regulations.gov docket ID or document ID.

### Agency rule or file code

Example:

```text
CMS-0062-P
```

This agency identifier appears in the docket title/abstract or document text.
The suffix can communicate phase, such as `P` for a proposed action, but code
should not infer every process relationship from naming alone.

### Federal Register document number

Example:

```text
2026-07205
```

`frDocNum` links the Regulations.gov document conceptually to its Federal
Register publication. It is distinct from a Federal Register citation, RIN,
docket ID, and agency file code.

### Tracking number

Example:

```text
mph-2mlk-j238
```

The comment `trackingNbr` is submission-oriented metadata, not the canonical
public comment resource ID.

## Core joins

### Docket to documents

```text
docket.data.id
    = document.data.attributes.docketId
```

This identifies all document resources placed in that docket. It does not imply
that every document is the same phase or version.

### Docket to comments

```text
docket.data.id
    = comment.data.attributes.docketId
```

This groups comments into a docket.

### Comment to commented-on document

```text
comment.data.attributes.commentOnDocumentId
    = document.data.id
```

This is the central direct edge used by this repository to build the finite
Stage 3 target registry.

An observed secondary join is:

```text
comment.data.attributes.commentOn
    = document.data.attributes.objectId
```

Use it as corroboration rather than the preferred public identifier.

### Comment to attachment

API relationship:

```text
comment.data.relationships.attachments.data[*].id
    = included attachment.id
```

Mirrored filename convention:

```text
<comment.data.id>_attachment_<docOrder>.<format>
```

### Original attachment to derived extraction

Mirrulations filename relationship:

```text
<comment-id>_attachment_<n>.pdf
    ↔ <comment-id>_attachment_<n>_extracted.txt
```

This is a Mirrulations/storage join, not a Regulations.gov API relationship
field.

## Regulatory phases

Federal rulemaking commonly follows a sequence such as:

```text
statutory authority or policy need
    ↓
advance notice, request for information, or proposed rule
    ↓
public comment period
    ↓
public comments and supporting attachments
    ↓
agency review and response to comments
    ↓
final rule, later proposal, withdrawal, or other disposition
    ↓
effective, compliance, and implementation dates
```

Real proceedings can branch, repeat, reopen, or omit phases. A docket can hold
notices, supporting material, extensions, corrections, proposed rules, final
rules, and other records.

### Initial regulatory action

The initial action relevant to comments may be:

- a proposed rule;
- an advance notice of proposed rulemaking;
- a notice;
- a request for information;
- another document inviting public participation.

The current docket's target document uses:

```text
documentType = Proposed Rule
```

It also contains labeled Requests for Information within the proposed rule.
Document type and internal discourse role are therefore separate concepts.

### Comment period

The regulatory document can provide:

- `commentStartDate`;
- `commentEndDate`;
- `openForComment`;
- `withinCommentPeriod`.

These describe the public-comment opportunity associated with that document.
They should not be used as the only evidence of process phase because values can
change over time and records can allow late comments.

### Public submissions

Comments identify their immediate regulatory target through
`commentOnDocumentId`. A comment can:

- support the action;
- oppose a proposal;
- answer an explicit open question;
- challenge an implicit agency assumption;
- propose implementation details;
- raise an issue the agency did not ask about;
- attach evidence or a full comment letter.

The form body and every attachment remain separately inspectable
representations. Analytical code should preserve the comment/submission
identity while avoiding duplicate counting of file formats.

### Later or final regulatory action

A final rule commonly:

- describes the proposal;
- summarizes comments;
- responds to comments;
- adopts, changes, or declines proposals;
- supplies effective or compliance dates;
- publishes regulatory text.

However, Regulations.gov does not guarantee that a later action can be joined
to an earlier proposal solely by one universal field. Depending on the record,
use a combination of:

- docket membership;
- RIN;
- agency file/rule identifier;
- Federal Register document numbers and citations;
- titles and explicit references in document text;
- agency metadata;
- publication chronology.

A later action may appear in the same docket or a related/new docket. Never
infer proposal-to-final identity merely because titles are similar.

## Structural relationship graph

A useful conceptual graph is:

```text
Agency
  └── HAS_DOCKET → Docket
        ├── HAS_DOCUMENT → RegulatoryDocument
        │     ├── HAS_CONTENT_FORMAT → HTML/PDF/etc.
        │     └── MAY_PRECEDE_OR_FOLLOW → RegulatoryDocument
        └── HAS_COMMENT → Comment
              ├── COMMENTS_ON → RegulatoryDocument
              ├── HAS_ATTACHMENT → AttachmentResource
              │     └── HAS_RAW_FORMAT → PDF/DOCX/etc.
              └── HAS_FORM_BODY → Comment text, when present

RawAttachment
  └── DERIVED_AS → ExtractedText

ExtractedText or form body
  └── RENDERED_AS → Markdown document
        └── HAS_BLOCK → Semantic block
              └── LINKS_BACK_TO → Regulatory-document block
```

Only some edges are explicit Regulations.gov fields:

- docket membership through `docketId`;
- comment target through `commentOnDocumentId`;
- attachments through `relationships.attachments`.

Edges such as `MAY_PRECEDE_OR_FOLLOW`, `DERIVED_AS`, and semantic-block links
are inferred or generated by Mirrulations and this repository and must preserve
their provenance.

## Search records versus detail records

The official Regulations.gov documentation distinguishes search endpoints from
detail endpoints:

```text
GET /v4/documents
GET /v4/documents/{documentId}

GET /v4/comments
GET /v4/comments/{commentId}

GET /v4/dockets
GET /v4/dockets/{docketId}
```

Search responses support filtering and pagination but can expose fewer fields.
Detail records provide richer attributes and relationships. Do not assume that
a field missing from a search result is absent from the detail resource.

The official documentation also warns that v4 pagination is bounded. A complete
historical corpus should rely on Mirrulations' bounded mirror/inventory and
verification rather than assuming one API page contains a whole docket.

## Duplicate-looking mirrored JSON filenames

The observed source tree can contain names such as:

```text
CMS-2026-1255-0001.json
CMS-2026-1255-0001(1).json
CMS-2026-1255-0001(2).json
```

Do not assume these are independent regulatory phases from filename alone.
They can represent repeated or colliding mirrored objects produced by upstream
collection history. Compare:

- embedded `data.id` and `data.type`;
- complete bytes and hashes;
- modification dates;
- attributes;
- source inventory records.

This repository's logical-document selection and source hashing exist partly to
avoid treating filename stems as sufficient identity.

## How this repository selects readable documents

The Markdown pipeline inventories every source asset and classifies it by file
suffix:

- `.htm`, `.html`, `.txt`, and eligible `.json` are potential Markdown sources;
- `.pdf`, `.docx`, and image files are structural sources;
- unsupported files remain inventoried but are not silently converted.

Selection rules include:

1. HTML and text are selected as readable text representations.
2. JSON is selected only when `data.attributes.comment` is a nonempty string.
3. Other JSON is metadata-only.
4. Original PDF/DOCX/image files supply structure and provenance rather than a
   second free-standing Markdown document.

Every selected asset receives:

- `source_object_key`;
- SHA-256 of exact source bytes;
- byte size and modification time;
- source suffix and role;
- structure status;
- deterministic Markdown path.

## How comment targets are selected

For a comment form body, the pipeline reads its own comment JSON. For an
extracted attachment, it derives the public comment ID from the filename and
locates the corresponding comment JSON.

It then reads:

```text
comment.attributes.commentOnDocumentId
```

and constructs an allowed target such as:

```json
{
  "target_key": "document:CMS-2026-1255-0001",
  "scope_type": "specific_document",
  "docket_id": "CMS-2026-1255",
  "document_ids": ["CMS-2026-1255-0001"],
  "document_type": "Proposed Rule",
  "agency_rule_identifier": "CMS-0062-P",
  "title": "...",
  "scope_label": "this proposed rule CMS-0062-P ..."
}
```

This finite target registry prevents the Stage 3 model from inventing unrelated
regulatory targets.

## Recommended analysis joins

### Build a docket inventory

1. Load the docket detail record.
2. Inventory all document JSON records where `attributes.docketId` matches.
3. Inventory all comment JSON records where `attributes.docketId` matches.
4. Keep `documents`, `comments`, and `attachments` as distinct node types.
5. Record every source object's hash and complete mirrored path.

### Reconstruct one public comment

1. Load the comment JSON by public comment ID.
2. Preserve the form body if `attributes.comment` is substantive.
3. Enumerate `relationships.attachments.data` and top-level `included` records.
4. Locate original binary files by comment ID and attachment ordinal.
5. Locate generated extractions by the same tuple.
6. Use pairing metadata to choose canonical text and structural sources.
7. Do not count alternate PDF/DOCX formats as separate submissions.
8. Do not merge the form body and attachment into one source-demarcated
   Markdown document unless an explicit later analysis layer requests it.

### Find the immediate action commented upon

1. Read `commentOnDocumentId`.
2. Find a document resource whose `data.id` matches exactly.
3. Confirm docket membership.
4. Optionally corroborate `commentOn` against document `objectId`.
5. Use the document's content HTML/text for substantive linking, not its JSON
   metadata fields alone.

### Link a proposal to a final action

1. Identify candidate later regulatory documents by chronology and
   `documentType`.
2. Compare docket IDs, RINs, agency rule/file codes, Federal Register metadata,
   and titles.
3. Read the later action for explicit references to the proposal and comments.
4. Preserve uncertainty when candidates conflict.
5. Record the evidence used for the cross-phase relationship.

## Common mistakes to avoid

- **Do not call all docket records "documents."** Comments and dockets are
  separate API resource types.
- **Do not call the docket the proposed rule.** The docket is a container.
- **Do not use the docket ID as the document ID.** They identify different
  resources.
- **Do not use the attachment's opaque resource ID as the comment ID.**
- **Do not treat the form-body placeholder as the full attached comment.**
- **Do not count PDF, DOCX, and extracted TXT formats as separate comments.**
- **Do not treat derived text as exact original bytes or exact layout.**
- **Do not discard the original binary after extracting text.**
- **Do not assume `data.attributes.comment` is always present or substantive.**
- **Do not infer a final-rule relationship from title similarity alone.**
- **Do not assume all phases occur in one docket.**
- **Do not assume one docket contains only one proposed or final action.**
- **Do not confuse RIN, docket ID, agency rule code, Federal Register document
  number, object ID, tracking number, and public resource ID.**
- **Do not assume a missing public field was never submitted.** Public API
  visibility and agency configuration affect available comment fields.
- **Do not infer source identity from a basename alone.** Use full object key,
  embedded resource ID, and content hash.
- **Do not edit the source mirror to fix extraction problems.** Create a
  versioned downstream derivative with provenance.

## Relationship to the rich Markdown database

The source hierarchy described here feeds the Markdown hierarchy documented in
[`RichDocumentStructure.md`](RichDocumentStructure.md):

```text
Regulations.gov resource metadata
    + Mirrulations raw text/binary content
    + Mirrulations derived extraction
        ↓
logical document selection and source pairing
        ↓
semantic blocks and Stage 1 Markdown
        ↓
citation-enriched Stage 2
        ↓
Stage 3 backward-reference descriptions
        ↓
Stage 4 exact links from comment blocks to regulatory-document blocks
```

The source mirror remains immutable pipeline input. The Markdown database and
its metadata remain rebuildable derivatives outside that mirror.

## Maintenance guidance

When Mirrulations or Regulations.gov changes:

1. verify the official API documentation and actual mirrored records;
2. distinguish API changes from Mirrulations path changes;
3. preserve source hashes and old derived provenance;
4. update pairing and selection tests before changing assumptions;
5. update this document with new resource fields or path conventions;
6. update `RichDocumentStructure.md` when downstream Markdown or metadata
   contracts change.

Future language models should use this document to understand source-level
regulatory identity and use `RichDocumentStructure.md` to understand the
downstream semantic and analytical representation.