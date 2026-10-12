# Regulations.gov API Examples

This directory is a small, browsable demonstration of how to download and join
metadata from the [Regulations.gov v4 API](https://open.gsa.gov/api/regulationsgov/).

It contains:

- [`download_examples.py`](download_examples.py), a deliberately simple and
  heavily commented example downloader;
- [`results/manifest.json`](results/manifest.json), the hard-coded list of
  examples selected for this demonstration; and
- the complete JSON detail responses for the selected documents, dockets, and
  comments.

The examples cover five document records in each of 28 regulatory-process and
Privacy Act categories. One document appears in two categories, so the 140
category placements represent 139 unique documents.

## What is included

```text
examples/regulation_gov_results/
├── README.md
├── download_examples.py
└── results/
    ├── manifest.json
    ├── documents/       139 document detail responses
    ├── dockets/         121 docket detail responses
    └── comments/         78 comment detail responses
```

Each resource file preserves the API's JSON:API-style detail envelope:

```json
{
  "data": {
    "id": "...",
    "type": "documents",
    "attributes": {}
  }
}
```

The JSON is pretty-printed and has sorted object keys so it is easy to browse
and produces stable Git diffs.

## What the examples demonstrate

The manifest contains five selected documents for each of these categories:

- request for information;
- advance notice of proposed rulemaking;
- notice of proposed rulemaking;
- supplemental proposed rule;
- comment-period reopening or extension;
- public meeting, hearing, or listening session;
- negotiated rulemaking;
- direct final rule and direct-final-rule withdrawal;
- interim final rule and final rule;
- correction;
- effective-date delay and compliance-date extension;
- amendment, withdrawal, rescission, and petition;
- supporting and related material;
- regulatory impact and regulatory flexibility analyses;
- information-collection and environmental analyses;
- response-to-comments material;
- OMB or interagency-review material; and
- initial, modified, and rescinded System of Records Notices.

These are all `documents` in the API. Regulations.gov does not provide separate
ANPRM, NPRM, final-rule, or SORN API resource endpoints. The stage or artifact
is represented by combinations of:

- `documentType`;
- `subtype`;
- `title` and `docAbstract`;
- Federal Register metadata;
- dates; and
- docket context.

For the complete interpretation of these fields and categories, read
[`../../RegulationsGovRegulatoryProcessMetadata.md`](../../RegulationsGovRegulatoryProcessMetadata.md).

## How the example downloader works

The script is intentionally not a framework or a production bulk downloader.
It demonstrates four basic API operations in plain Python.

### 1. Download document detail

For every hard-coded document ID in the manifest, it requests:

```text
GET https://api.regulations.gov/v4/documents/{documentId}
```

It writes the response to `results/documents/{documentId}.json`.

### 2. Follow the document to its docket

Document detail contains `attributes.docketId`. The script requests:

```text
GET https://api.regulations.gov/v4/dockets/{docketId}
```

It writes each unique docket once. Docket detail is where fields such as the
Regulation Identifier Number (`rin`) can appear.

The direct join is:

```text
document.attributes.docketId = docket.data.id
```

### 3. Search for comments on the document

This is the most important non-obvious part of the example. The comments search
does **not** use the public document ID. It uses the document's opaque
`attributes.objectId`:

```text
GET /v4/comments?filter[commentOnId]={document.objectId}&page[size]=5
```

The example asks for at most five comments per document, ordered by
`postedDate`. A zero-result search means no comments are directly linked to
that document object. It does not prove that the broader docket received no
comments.

### 4. Validate the readable comment link

For every returned comment summary, the script downloads comment detail:

```text
GET https://api.regulations.gov/v4/comments/{commentId}
```

Comment detail supplies the readable public-document join:

```text
comment.attributes.commentOnDocumentId = document.data.id
```

The equivalent opaque join is:

```text
comment.attributes.commentOn = document.attributes.objectId
```

The script downloads comment metadata only. It does not download comment
attachments.

## API key setup

Regulations.gov requires an API key in the `X-Api-Key` HTTP header. Obtain one
through [api.data.gov](https://api.data.gov/signup/), then export it:

```shell
export REGULATIONS_GOV_API_KEY="your-key-here"
```

Alternatively, place it in an ignored dotenv file:

```dotenv
REGULATIONS_GOV_API_KEY=your-key-here
```

Never commit an actual API key. The downloader reads the key but never prints
or writes it.

## Redownload the checked-in results

From the repository root, using an exported key:

```shell
.venv/bin/python examples/regulation_gov_results/download_examples.py
```

Or load the repository's ignored `.env` explicitly:

```shell
.venv/bin/python examples/regulation_gov_results/download_examples.py \
  --dotenv .env
```

The default half-second pause is intentionally conservative. To write into a
temporary directory without changing the checked-in examples:

```shell
.venv/bin/python examples/regulation_gov_results/download_examples.py \
  --dotenv .env \
  --output-directory /tmp/regulation-gov-results
```

API records are live data. A later download can legitimately differ from the
checked-in snapshot if an agency modifies public metadata.

## Why the manifest is hard-coded

The purpose of this directory is to memorialize known examples, not to repeat a
full-text discovery search whose ranking can change. The manifest therefore
contains the exact selected public document IDs grouped by category.

The downloader reads those IDs, fetches current document details, and discovers
the related docket and comments through live API fields. This keeps selection
reproducible while still demonstrating the real relationships.

## Interpreting the results

Keep these cautions in mind:

1. Docket co-membership does not prove that two documents are versions of one
   another.
2. Full-text search terms are not exact lifecycle classifications.
3. `documentType` is broad, and `subtype` varies by agency and record age.
4. Final rules usually do not receive comments directly; comments ordinarily
   point to an earlier proposed rule.
5. Supporting analyses usually relate to a solicitation or rule but are not
   themselves the document on which comments were submitted.
6. SORNs are Privacy Act notices, not APA rulemaking stages, even though their
   metadata can include comment-period fields.
7. Unified Agenda entries and OIRA review events are external to the three
   Regulations.gov resource families.

## Snapshot provenance

The checked-in snapshot was generated from the validated research collection
described in
[`../../RegulationsGovRegulatoryProcessMetadata.md`](../../RegulationsGovRegulatoryProcessMetadata.md).
The timestamp is recorded in `results/manifest.json`. All sampled comment
details were checked to ensure that `commentOnDocumentId` matched the selected
public document ID.
