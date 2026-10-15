# Mirrulations Regulation Data

Mirrulations Regulation Data is an auditable ETL and analysis system that turns
a bounded public regulatory docket into immutable, citation-aware Markdown;
discovers document structure and exact backward references; extracts agency
proposals and feedback requests; models topical clusters across public comments;
and publishes a local comment browser and deterministic Neo4j graph for
exploring how regulatory anchors, comments, topics, citations, and source
passages relate.

- [Using the analysis system](usage.md) — start the completed system, open the
  force-directed topical overview, query Neo4j, and drill into source passages.
- [Architecture](architecture.md) — understand the Markdown database,
  authoritative sidecars, graph schema, identifiers, and projections.
- [Pipeline](pipeline.md) — create provider API keys, run every ETL stage,
  resume paid work, and validate outputs.
- [Other documentation](other.md) — retained operational notes, data license,
  warnings, S3 background, and Mirrulations storage notes.
- [Generated Markdown contract](RichDocumentStructure.md) — detailed semantic
  Markdown and metadata contract.
- [Corrected Mirrulations storage guide](MirrulationsStructureCorrected.md) —
  corrected source-bucket and JSON layout.
- [Pinned upstream storage guide](MirrulationsStructureUpstream.md) — exact
  upstream structure reference.
- [Regulatory resource traversal](MirrulationsRegulatoryDocumentStructure.md) —
  how regulatory resources connect in the source corpus.
- [Regulations.gov metadata](RegulationsGovRegulatoryProcessMetadata.md) —
  process metadata and system-of-record notices.
