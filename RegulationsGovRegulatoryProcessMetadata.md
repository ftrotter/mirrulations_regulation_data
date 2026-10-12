# Regulations.gov Regulatory Process Metadata

This guide explains how federal regulatory-process artifacts appear in the
Regulations.gov v4 API, how their metadata differs, and how dockets, documents,
comments, Federal Register publications, and external regulatory systems link
together.

It is based on 140 document-detail records: five examples in each of 28
artifact categories. The research also retrieved 135 docket-detail records and
78 comment-detail records. Every sampled comment was joined to its target
document successfully.

The compact, machine-readable evidence is
[`data/regulations_gov_research/evidence_summary.json`](data/regulations_gov_research/evidence_summary.json).
The complete responses and collection manifest are under
`data/regulations_gov_research/`.

## Scope and important limitations

Regulations.gov does not encode the regulatory lifecycle as a workflow. Its
first-class searchable resources are:

1. `dockets`;
2. `documents`; and
3. `comments`.

An ANPRM, NPRM, final rule, hearing notice, analysis, or SORN is a **document**
resource classified by some combination of `documentType`, `subtype`, title,
dates, and docket context. These are not separate API resource types.

The API uses a broad detail schema. In this study, all 140 document details
contained the same 68 attribute keys, all 135 docket details contained the same
21 keys, and all 78 comment details contained the same 47 keys. Many values are
null. Differences among artifacts are therefore mostly differences in values,
classifications, populated dates, and relationships—not different JSON object
shapes.

Search is full-text and noisy. A search for `Final Rule` can return a final
rule, an analysis of a final rule, or a document that merely cites one. Never
treat `filter[searchTerm]` as an exact lifecycle classifier.

## Evidence method

The collector:

- uses the v4 documents search to identify candidates;
- applies exact `documentType` and `subtype` filters when possible;
- validates titles and detail metadata;
- retrieves the containing docket when one exists;
- searches for comments using the document's opaque `objectId`;
- retrieves up to five comment details for each selected document;
- writes pretty-printed, cached JSON; and
- can resume without repeating completed requests.

The collection ran on October 12, 2026. API records can subsequently change.

## The three API resources

### Docket

A docket is a public container, not a document and not necessarily the entire
regulatory action.

Important fields include:

| Field | Meaning |
|---|---|
| `data.id` | Public docket ID, such as `CMS-2026-1255` |
| `agencyId` | Owning agency code |
| `docketType` | Broad process type, commonly `Rulemaking` or `Nonrulemaking` |
| `title`, `dkAbstract` | Docket-level description |
| `rin` | Regulation Identifier Number when supplied |
| `objectId` | Opaque internal identity |

The RIN belongs to docket detail in v4. It is not returned as a document-search
field and is not interchangeable with a docket ID.

### Document

A document represents a public regulatory artifact or submission-related item.

Important fields include:

| Field | Meaning |
|---|---|
| `data.id` | Public document ID |
| `docketId` | Containing docket |
| `documentType` | Broad classification |
| `subtype` | More specific, agency-configurable classification |
| `title`, `docAbstract` | Human-readable description |
| `frDocNum` | Federal Register document number |
| `cfrPart` | Referenced CFR parts when supplied |
| `commentStartDate`, `commentEndDate` | Solicitation window |
| `effectiveDate`, `implementationDate` | Operative dates when supplied |
| `openForComment`, `withinCommentPeriod` | Current API state |
| `withdrawn`, `reasonWithdrawn` | API withdrawal state and reason |
| `objectId` | Opaque identity used by comment search |
| `fileFormats` | Available representations and attachments |

`withdrawn` is the API's document-status indicator. A title containing
“withdrawal” is not equivalent to `withdrawn: true`: a posted withdrawal notice
is itself normally an active document describing withdrawal of another action.

### Comment

A public comment is returned by the comments endpoints and ordinarily has
`documentType: "Public Submission"` and a subtype such as `Public Comment`.

Important fields include:

| Field | Meaning |
|---|---|
| `data.id` | Public comment ID |
| `docketId` | Containing docket |
| `commentOnDocumentId` | Public ID of the document directly commented on |
| `commentOn` | Opaque object ID of that document |
| `comment` | Form-submitted text or attachment placeholder |
| `title` | Usually identifies the target document |
| `organization`, name fields | Public submitter information when available |
| `postedDate`, `receiveDate` | Publication and receipt dates |
| `trackingNbr` | Submission tracking identity, not the public comment ID |
| `fileFormats` | Comment file/attachment representations |

## The critical comment-join trap

The search endpoint is named as though it accepted a public document ID:

```text
GET /v4/comments?filter[commentOnId]=...
```

In observed behavior, it requires the target document's opaque `objectId`:

```text
document.attributes.objectId
    -> filter[commentOnId]
```

For the known proposal `CMS-2026-1255-0001`, searching with that public ID
returned zero comments. Searching with its `objectId`,
`09000064b927bd06`, returned 721.

After retrieval, the durable human-readable join is:

```text
comment.attributes.commentOnDocumentId
    = document.data.id
```

The equivalent opaque join is:

```text
comment.attributes.commentOn
    = document.attributes.objectId
```

All 78 sampled comment details satisfied the public-ID join.

## Regulatory artifact fingerprints

The classifications below describe observed API records, not a closed or
agency-independent vocabulary. `subtype` is especially inconsistent across
agencies and historical migrations.

### Pre-proposal and proposal artifacts

| Artifact | Common metadata fingerprint | Process role |
|---|---|---|
| RFI | Often `documentType: Other`, `subtype: Request`; title supplies “Request for Information” | Collects facts before or outside a proposal |
| ANPRM | `documentType: Proposed Rule`; frequently `subtype: Advance Notice of Proposed Rulemaking (ANPRM)` | Seeks early input before specific proposed text |
| NPRM | `documentType: Proposed Rule`; subtype may be null or `Federal Register Document` | Proposes regulatory text and opens comment |
| Supplemental NPRM | Ideally `documentType: Proposed Rule`, but many search results are prior-publication or supporting copies | Supplements or changes an earlier proposal |
| Negotiated rulemaking | Observed as `Proposed Rule` or `Notice`; subtype varies | Establishes or reports stakeholder negotiation |
| Reopening/extension | `Notice` or `Proposed Rule`; subtype can be `Reopening of Comment Period` | Changes the solicitation window |
| Meeting/hearing notice | Usually `documentType: Notice`; subtypes include `Meeting` and `Public Meetings` | Announces oral or participatory proceedings |

The five RFI examples selected by exact title had no comments directly linked
to those specific records. That does not establish that RFIs lack comments;
agencies can place a solicitation and submissions in different records or use
other titles and classifications.

Two of five sampled ANPRMs and four of five sampled NPRMs had directly linked
comments. The sampled ANPRM documents collectively reported 3,556 comments;
the sampled NPRMs reported 2,838.

### Alternative and final-rule paths

| Artifact | Common metadata fingerprint | Process implication |
|---|---|---|
| Direct final rule | Often `documentType: Rule`, but notices and supporting copies also use the phrase | Takes effect unless adverse comment triggers withdrawal |
| Direct-final withdrawal | Usually a separate `Rule` or `Notice` whose title contains both withdrawal and direct final rule | Cancels the direct final action; it is not merely `withdrawn: true` |
| Interim final rule | `documentType: Rule`; subtype may be `Interim Final Rule`, `Final Rule`, or null | Rule is issued before ordinary pre-promulgation comment; post-publication comments may follow |
| Final rule | `documentType: Rule`; commonly `subtype: Final Rule` | Adopts provisions and responds to significant comments |
| Effective-date delay | Commonly `documentType: Rule`; title carries the delay | Changes when an earlier rule becomes operative |
| Compliance-date extension | Can be a `Rule` or `Proposed Rule`; related review material also uses the phrase | Changes when regulated parties must comply |
| Correction | Classification varies widely; titles and Federal Register linkage are essential | Corrects publication or regulatory text |
| Withdrawal | Can be `Other`, `Notice`, `Rule`, or supporting material | Must identify what was withdrawn and at what phase |
| Rescission/repeal | No reliable universal subtype; title and linked action control | Removes an existing action or regulation through the applicable process |

Two of five sampled interim final rules had direct comments. None of the five
sampled final rules did. This is expected: comments normally target the
proposal, while the final rule is a later document in the same or a related
docket. Finding comments for a final rule therefore requires traversing to its
antecedent proposal rather than querying the final rule alone.

### Supporting and administrative-record artifacts

| Artifact | Common metadata fingerprint | Relationship |
|---|---|---|
| Generic supporting material | `documentType: Supporting & Related Material` | Evidence or context for another action |
| Regulatory Impact Analysis | Usually supporting material; subtypes include `Regulatory Analysis`, `Impact Analysis Report`, and `Supplement` | Cost-benefit and alternative analysis |
| Regulatory Flexibility Analysis | Usually supporting material; subtype is inconsistent | Small-entity analysis |
| Information Collection/PRA material | Usually supporting material; subtypes include `Data` and `Memorandum` | Supports an ICR and burden analysis |
| Environmental analysis | `Supporting & Related Material` or `Other`; subtype can be `Environmental Impact Statement` | NEPA or other environmental review |
| Response to comments | `Other` or supporting material; subtypes include `Response(s)` | Agency or party response; may also be embedded in a final-rule preamble |
| OMB/interagency review material | Supporting material; often subtype `Office of Management and Budget (OMB)` | Public docket evidence of review, not the OIRA review event itself |
| Petition | Often `Other`, with subtype `Petition for Rulemaking` or `Petition(s)` | Possible initiating event |

These documents usually do not receive comments directly. They support the
document that opened the comment opportunity. Docket co-membership alone does
not say which proposal, final rule, or analysis they support; titles, Federal
Register numbers, RINs, dates, and document text may be needed.

### Comment evidence by category

Direct comment records were found for at least one of the five examples in
these categories:

- ANPRM;
- NPRM;
- supplemental NPRM;
- public meeting/hearing;
- negotiated rulemaking;
- interim final rule;
- compliance-date extension;
- environmental analysis;
- initial SORN; and
- modified SORN.

Zero direct comments for a selected document means only that the comments API
did not link comments to that document's `objectId`. It does not prove that the
broader docket or regulatory action received no comments.

## SORNs: a parallel Privacy Act notice process

A System of Records Notice is not an APA rulemaking stage. It is a Privacy Act
notice describing a federal system of records. Under 5 U.S.C. § 552a(e)(4) and
OMB Circular A-108, a SORN identifies matters including:

- the system and its purposes;
- authority for maintaining records;
- categories of records and individuals;
- routine uses;
- storage, retrieval, safeguards, retention, and disposal; and
- access, contesting, and notification procedures.

### SORN lifecycle

1. **Initial SORN.** Publish when establishing a new system of records.
2. **Modified SORN.** Publish for significant substantive changes, including
   expanded populations or record categories, changed purposes or authority,
   changed operation, or a new/significantly modified routine use.
3. **Rescindment.** Publish when the agency stops maintaining the system. The
   notice explains why and what happens to the records, including migration to
   another system when applicable.

A new or revised SORN is generally effective on Federal Register publication.
A new or significantly modified routine use is different: it cannot become the
basis for disclosure until at least 30 days after publication, after the agency
has allowed and considered public comment. Significant post-comment changes can
require another 30-day period.

Agencies must provide advance reports for new or significantly modified systems
to OMB and Congress before Federal Register publication. Privacy Act exemption
rules are separate rulemaking documents and may undergo ordinary regulatory
review.

### SORN metadata fingerprint

Initial and modified SORNs were consistently observed as:

```json
{
  "documentType": "Notice",
  "subtype": "System of Records"
}
```

The title distinguishes new from modified notices. Rescindments in the sample
were `documentType: Notice` with a null subtype; the title supplied
`Rescindment`. Therefore, subtype alone cannot recover the complete SORN
lifecycle.

Three of five initial SORNs and three of five modified SORNs had direct comment
records. The five sampled rescindments had none.

## Direct, indirect, inferred, and external links

### Direct API joins

```text
docket.data.id
    = document.attributes.docketId
    = comment.attributes.docketId
```

```text
document.data.id
    = comment.attributes.commentOnDocumentId
```

```text
document.attributes.objectId
    = comment.attributes.commentOn
    = comments-search filter[commentOnId]
```

### Strong cross-system identifiers

| Identifier | Connects to |
|---|---|
| `frDocNum` | FederalRegister.gov/API publication record |
| docket `rin` | Unified Agenda/Reginfo.gov regulatory action |
| `cfrPart` | CFR subject location; not a version-specific amendment join |
| agency rule number in title/text | Agency-specific proposal/final identifiers |

`frDocNum` is document-specific. A RIN is action-oriented and can span multiple
Federal Register publications. Neither should be replaced by docket
co-membership.

### Inferred lifecycle edges

Regulations.gov does not normally provide explicit fields such as
`finalizesDocumentId`, `supplementsDocumentId`, or `correctsDocumentId`.
Relationships among regulatory documents often require combining:

- docket membership;
- RIN;
- Federal Register document numbers and citations;
- agency rule identifiers;
- titles and dates;
- references in abstracts or document text; and
- comments' direct target IDs.

Such edges should be labeled inferred unless the source text explicitly names
the relationship.

### Processes outside Regulations.gov

The following are not first-class Regulations.gov resources:

- statutes and court decisions that initiate action;
- internal drafting and agency clearance;
- Unified Agenda planning entries;
- OIRA review events and review history;
- Congressional Review Act submissions;
- CFR codification and historical versions; and
- judicial-review cases and opinions.

Use Congress.gov or statutory sources, Reginfo.gov, FederalRegister.gov,
GAO's CRA database, GovInfo/eCFR, and court systems as appropriate. A docket may
contain supporting copies from those processes, but that does not turn the
external event into a Regulations.gov resource.

## Traversing one regulatory action

A robust traversal should:

1. Start from a known docket, document, comment, RIN, or Federal Register number.
2. Retrieve document detail and preserve both public `id` and opaque `objectId`.
3. Retrieve docket detail through `docketId` and record its RIN.
4. Enumerate docket documents; classify each using type, subtype, title, dates,
   Federal Register number, and text—not search terms alone.
5. Query comments on each solicitation document using its `objectId`.
6. Validate each comment through `commentOnDocumentId`.
7. Follow `frDocNum` to the Federal Register publication and its structured
   metadata.
8. Follow the RIN to Unified Agenda and OIRA records.
9. Infer proposal-to-final, correction, delay, withdrawal, and supporting
   relationships only when corroborated.
10. Record uncertainty and provenance for every inferred edge.

## HTML, HTM, and JSON roles

Regulations.gov JSON supplies resource identity, classification, dates, joins,
and file inventories. HTML or HTM files commonly contain the authoritative
readable notice, preamble, or regulatory text needed to recover relationships
that are absent from JSON. Attachments can contain analyses or comments whose
metadata exists in JSON but whose substantive content does not.

Therefore:

- use JSON for exact resource and identifier relationships;
- use HTML/HTM for explicit narrative cross-references and process language;
- use attachment content for evidence and comment substance; and
- never infer that two files are the same logical artifact merely because they
  share a docket.

## Reproducing the evidence

Set `REGULATIONS_GOV_API_KEY` in the environment or an ignored dotenv file and
run:

```shell
.venv/bin/python scripts/regulations_gov_research.py \
  --dotenv .env \
  --output-root data/regulations_gov_research \
  --sample-size 5 \
  --search-size 100 \
  --requests-per-second 2
```

The API key is neither printed nor stored. Cached responses make reruns
resumable.

## Authorities

- [Regulations.gov API documentation](https://open.gsa.gov/api/regulationsgov/)
- [Regulations.gov v4 OpenAPI specification](https://open.gsa.gov/api/regulationsgov/v4/openapi.yaml)
- [The Reg Map: Informal Rulemaking](https://www.reginfo.gov/public/reginfo/Regmap/REG_MAP_2020.pdf)
- [OMB Circular A-108](https://www.whitehouse.gov/wp-content/uploads/legacy_drupal_files/omb/circulars/A108/omb_circular_a-108.pdf)
- [Privacy Act, 5 U.S.C. § 552a](https://www.govinfo.gov/link/uscode/5/552a)
