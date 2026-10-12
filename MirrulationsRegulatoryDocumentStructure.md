# Mirrulations Regulatory Document Structure

This guide explains how to traverse regulatory records mirrored by
Mirrulations. For storage paths and JSON shapes, start with
[`MirrulationsStructureCorrected.md`](MirrulationsStructureCorrected.md).

For the real-world process, see the official
[Reg Map PDF](https://www.reginfo.gov/public/reginfo/Regmap/REG_MAP_2020.pdf).

## Four layers

| Layer | Contents | Authority |
|---|---|---|
| Regulations.gov | Dockets, documents, comments, file metadata | Resource identity and public metadata |
| Mirrulations raw | API JSON, HTML/HTM, original attachments | Downloaded source bytes |
| Mirrulations derived | Extracted text and other generated files | Method-specific derivative |
| Markdown database | Semantic blocks, citations, references, links | This repository's analysis |

Do not treat a docket as one document, an extraction as an original, or every
record in one docket as one phase of rulemaking.

## Core graph

```text
docket
├── regulatory documents
│   ├── RFI / ANPRM / proposed rule
│   ├── notices / meetings / supporting analyses
│   └── final rule / correction / delay / withdrawal
└── comments ──commentOnDocumentId──> solicitation document
    └── attachments ──> derived text
```

Regulations.gov has three searchable resource families: `dockets`, `documents`,
and `comments`. Attachments are related file resources. Regulatory stages are
document classifications, not separate API resource types.

## Direct joins

```text
docket.data.id = document.attributes.docketId
docket.data.id = comment.attributes.docketId
document.data.id = comment.attributes.commentOnDocumentId
document.attributes.objectId = comment.attributes.commentOn
```

To search comments on a document:

```text
GET /comments?filter[commentOnId]=<document.attributes.objectId>
```

The filter expects the opaque object ID. Validate results with the readable
`commentOnDocumentId`.

## Cross-stage links

Regulations.gov usually does not provide fields such as
`finalizesDocumentId` or `correctsDocumentId`. Build cross-stage links from:

1. explicit references in HTML/HTM or attachment text;
2. RIN;
3. Federal Register document number/citation;
4. agency rule identifier;
5. docket membership, title, and chronology.

Docket membership alone is weak evidence. Label inferred links and retain the
evidence used.

## Identifier map

| Identifier | Meaning |
|---|---|
| Docket ID | Public Regulations.gov container |
| Document/comment ID | Public API resource |
| `objectId` | Opaque API identity used by comment search |
| Attachment ID | Opaque file-resource identity |
| RIN | Unified Agenda/Reginfo.gov action |
| `frDocNum` | Federal Register publication |
| Tracking number | Comment submission tracking |

Never substitute one identifier for another.

## Traversal recipe

1. Retrieve document detail; retain public `id` and opaque `objectId`.
2. Follow `docketId` to docket detail; record the RIN.
3. Enumerate docket documents and classify from metadata plus content.
4. Query comments with the target document's `objectId`.
5. Validate each comment's `commentOnDocumentId`.
6. Follow `frDocNum` to FederalRegister.gov.
7. Follow RIN to Unified Agenda/OIRA records at Reginfo.gov.
8. Read HTML/HTM and attachments for explicit cross-stage relationships.
9. Record provenance and uncertainty for inferred edges.

## Common mistakes

- Counting attachments or formats as separate comments.
- Treating “See attached” as the full comment.
- Treating a final rule as the direct target of earlier proposal comments.
- Assuming all phases use one docket.
- Inferring lifecycle stage from full-text search alone.
- Editing raw files to repair extraction problems.
- Using a basename instead of full object key plus hash for provenance.

## Related guides

- [Artifact metadata and process evidence](RegulationsGovRegulatoryProcessMetadata.md)
- [Checked-in API examples](examples/regulation_gov_results/)
- [Generated Markdown contracts](RichDocumentStructure.md)
- [Exact upstream storage document](MirrulationsStructureUpstream.md)