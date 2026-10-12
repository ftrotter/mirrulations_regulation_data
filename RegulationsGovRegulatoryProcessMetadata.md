# Regulations.gov Process Metadata

Regulations.gov stores `dockets`, `documents`, and `comments`; it does not store
the regulatory lifecycle as a workflow. Read the official
[Reg Map PDF](https://www.reginfo.gov/public/reginfo/Regmap/REG_MAP_2020.pdf)
for the process, then use this guide to recognize its artifacts in API metadata.

Evidence: 140 category placements across 28 artifact categories, representing
139 unique documents, 121 dockets, and 78 sampled comments. Browse the
[checked-in JSON](examples/regulation_gov_results/) or the compact
[evidence summary](data/regulations_gov_research/evidence_summary.json).

## Resource fingerprints

| Artifact | Typical API metadata |
|---|---|
| RFI | Often `documentType: Other`, `subtype: Request`; title is essential |
| ANPRM | `Proposed Rule`; often subtype `Advance Notice of Proposed Rulemaking (ANPRM)` |
| NPRM | `Proposed Rule`; subtype can be null or `Federal Register Document` |
| Supplemental NPRM | Prefer `Proposed Rule`; supporting copies also use the phrase |
| Comment reopening | `Notice` or `Proposed Rule`; title/subtype carries reopening |
| Meeting/hearing | Usually `Notice`; subtype `Meeting` or `Public Meetings` |
| Direct final rule | Often `Rule`; notices and supporting copies also mention it |
| Interim final rule | `Rule`; subtype can be `Interim Final Rule`, `Final Rule`, or null |
| Final rule | `Rule`; commonly subtype `Final Rule` |
| Correction/delay/withdrawal | Type varies; title and referenced action control |
| Supporting analysis | Usually `Supporting & Related Material`; subtype varies |
| OMB review material | Supporting material; often subtype `Office of Management and Budget (OMB)` |
| Initial/modified SORN | `Notice`, subtype `System of Records` |
| SORN rescindment | `Notice`; subtype may be null, title carries rescindment |

`filter[searchTerm]` is full-text and noisy. Validate candidates with detail
metadata, docket context, Federal Register metadata, and content.

## Fields that matter

### Docket

| Field | Use |
|---|---|
| `data.id` | Public container ID |
| `docketType` | Rulemaking/nonrulemaking classification |
| `title`, `dkAbstract` | Action-level description |
| `rin` | Link to Unified Agenda/Reginfo.gov |

### Document

| Field | Use |
|---|---|
| `data.id` | Public document ID |
| `docketId` | Containing docket |
| `documentType`, `subtype` | Broad and specific classification |
| `title`, `docAbstract` | Human description and lifecycle clues |
| `frDocNum` | Federal Register publication link |
| comment/effective dates | Solicitation and operation timing |
| `withdrawn` | API status; not the same as a posted withdrawal notice |
| `objectId` | Opaque identity used by comments search |

### Comment

| Field | Use |
|---|---|
| `data.id` | Public comment ID |
| `docketId` | Containing docket |
| `commentOnDocumentId` | Public target document ID |
| `commentOn` | Target document's opaque `objectId` |
| `comment` | Form text or attachment placeholder |
| `fileFormats` | Available files/attachments |

## Comment lookup

```text
GET /comments?filter[commentOnId]=<document.attributes.objectId>
```

Then validate:

```text
comment.attributes.commentOnDocumentId = document.data.id
```

Zero direct comments does not mean zero docket comments. Final rules and
supporting analyses usually point back to an earlier solicitation that received
the comments.

## SORNs

A System of Records Notice is a Privacy Act notice, not an APA rulemaking stage.

1. Publish an initial SORN for a new system.
2. Publish a modified SORN for significant changes.
3. Publish a rescindment when the system is no longer maintained.

A SORN is generally effective on publication. New or significantly modified
routine uses require at least 30 days for public comment before use. Agencies
also report new/significantly modified systems to OMB and Congress before
publication. See
[OMB Circular A-108](https://www.whitehouse.gov/wp-content/uploads/legacy_drupal_files/omb/circulars/A108/omb_circular_a-108.pdf).

## External systems

These are not first-class Regulations.gov resources:

- statutes and court decisions;
- Unified Agenda entries;
- OIRA review events;
- Congressional Review Act submissions;
- CFR versions; and
- judicial-review cases.

Use RIN, `frDocNum`, citations, agency identifiers, and explicit text to cross
into Reginfo.gov, FederalRegister.gov, Congress/GAO, eCFR/GovInfo, and courts.

## Rules for robots and humans

1. Preserve public IDs and opaque IDs.
2. Treat type/subtype as evidence, not a complete ontology.
3. Prefer explicit textual relationships over title similarity.
4. Label inferred lifecycle edges.
5. Keep JSON for identity; read HTML/HTM and attachments for substance.

## Sources

- [Regulations.gov API](https://open.gsa.gov/api/regulationsgov/)
- [Regulations.gov OpenAPI](https://open.gsa.gov/api/regulationsgov/v4/openapi.yaml)
- [Reg Map PDF](https://www.reginfo.gov/public/reginfo/Regmap/REG_MAP_2020.pdf)
- [Checked-in examples and downloader](examples/regulation_gov_results/)