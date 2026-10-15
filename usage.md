# Using the Analysis System

This guide begins after the pipeline has produced Stage 5 Markdown and
`data/markdown_db/metadata/topic_graph/graph_bundle.json`. See
[pipeline.md](pipeline.md) if those files do not exist.

## Start the comment browser

The graph links back to a local read-only browser. Start it first so links from
Neo4j resolve:

```shell
.venv/bin/python scripts/comment_browser.py start \
  --markdown-db data/markdown_db
```

Open <http://127.0.0.1:8765/comments/>. The landing page searches whole comment
submissions. A submission can contain a form comment and one or more attachment
representations. Each representation page links to every available Markdown
stage; Stage 5 contains topic annotations.

Keep the browser at the address recorded in `COMMENT_BROWSER_BASE_URL` when the
graph was generated. A different host or port requires regenerating the topic
graph so its `Block.browser_url` values remain correct.

## Start Neo4j

Set a local password and start the Compose service:

```shell
export NEO4J_PASSWORD='choose-a-local-password'
docker compose up -d neo4j
docker compose ps
```

Open <http://127.0.0.1:7474>, connect to `neo4j://127.0.0.1:7687`, and sign in
as user `neo4j` with the selected password.

If those ports are occupied, stop the container and use alternate host ports:

```shell
export NEO4J_PASSWORD='choose-a-local-password'
export NEO4J_BROWSER_PORT=17474
export NEO4J_BOLT_PORT=17687
export NEO4J_URI=bolt://127.0.0.1:17687
docker compose up -d neo4j
```

Then open <http://127.0.0.1:17474> and connect to
`neo4j://127.0.0.1:17687`.

## Validate and import the graph

Validation does not require a running Neo4j database:

```shell
.venv/bin/python scripts/neo4j_graph.py validate \
  --bundle data/markdown_db/metadata/topic_graph/graph_bundle.json
```

Import after Neo4j is healthy:

```shell
.venv/bin/python scripts/neo4j_graph.py import \
  --bundle data/markdown_db/metadata/topic_graph/graph_bundle.json
```

Use `--uri bolt://127.0.0.1:17687` with the alternate port. The importer reads
`NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` from `.env` or the process
environment. Deterministic IDs and `MERGE` make repeated imports idempotent.

## Starting picture: topical comment clusters

The canonical overview contains:

- red regulatory anchors: agency `Proposal` and `FeedbackRequest` nodes;
- blue topical cluster centers: `Topic` nodes; and
- green whole-comment representations: comment `Document` nodes.

The pipeline aggregates accepted block assignments into
`Document -[:DISCUSSES_TOPIC]-> Topic`. Detailed evidence remains available as
`Block -[:ASSIGNED_TOPIC]-> Topic`.

Paste this query into Neo4j Browser:

```cypher
MATCH (anchor)-[anchor_relationship:ABOUT_TOPIC]->(topic:Topic)
WHERE anchor:Proposal OR anchor:FeedbackRequest
OPTIONAL MATCH (comment:Document)-[
  comment_relationship:DISCUSSES_TOPIC
]->(topic)
WHERE comment.role IN ['form_comment', 'comment_attachment']
RETURN anchor, anchor_relationship, topic, comment_relationship, comment
```

Select the graph result view. Neo4j Browser applies a force-directed layout.
Open the graph-style panel and use these captions and colors:

| Label | Caption | Suggested color |
| --- | --- | --- |
| `Topic` | `label` | blue |
| `Proposal` | `label` | red |
| `FeedbackRequest` | `label` | orange |
| `Document` | `document_id` | green |

Drag important topic nodes apart and zoom out to obtain the large summary
picture. Dense comment clouds reveal topical clusters; anchors show which
clusters originate in explicit agency proposals or requests for feedback.

For a less crowded overview, keep topics with at least ten whole comments:

```cypher
MATCH (topic:Topic)<-[comment_relationship:DISCUSSES_TOPIC]-
  (comment:Document)
WHERE comment.role IN ['form_comment', 'comment_attachment']
WITH topic, count(DISTINCT comment) AS comment_count
WHERE comment_count >= 10
OPTIONAL MATCH (anchor)-[anchor_relationship:ABOUT_TOPIC]->(topic)
WHERE anchor:Proposal OR anchor:FeedbackRequest
OPTIONAL MATCH (comment:Document)-[
  comment_relationship:DISCUSSES_TOPIC
]->(topic)
RETURN anchor, anchor_relationship, topic, comment_relationship, comment
```

## Drill down from a topic

List the busiest topics:

```cypher
MATCH (comment:Document)-[discussion:DISCUSSES_TOPIC]->(topic:Topic)
RETURN topic.label AS topic,
       count(DISTINCT comment) AS comments,
       sum(discussion.matched_block_count) AS matching_blocks,
       max(discussion.maximum_score) AS maximum_score
ORDER BY comments DESC, topic
```

Replace the example text below with a selected topic label to list comments:

```cypher
MATCH (comment:Document)-[discussion:DISCUSSES_TOPIC]->(topic:Topic)
WHERE topic.label = 'REPLACE WITH TOPIC LABEL'
RETURN comment.document_id AS comment_id,
       comment.title AS title,
       comment.role AS representation,
       discussion.matched_block_count AS matching_blocks,
       discussion.maximum_score AS maximum_score
ORDER BY matching_blocks DESC, maximum_score DESC
```

## Open the exact matching passage

Use a topic and comment ID to recover assigned blocks:

```cypher
MATCH (comment:Document)-[:HAS_VERSION]->(:DocumentVersion)-[:HAS_BLOCK]->
  (block:Block)-[assignment:ASSIGNED_TOPIC]->(topic:Topic)
WHERE topic.label = 'REPLACE WITH TOPIC LABEL'
  AND comment.document_id = 'REPLACE WITH COMMENT ID'
RETURN block.block_id AS block,
       left(block.plain_text, 300) AS passage,
       assignment.score AS score,
       block.browser_url AS open_in_comment_browser
ORDER BY score DESC, block.order
```

Copy `open_in_comment_browser` into a browser. It opens Stage 5 at the exact
semantic-block anchor, where neighboring paragraphs and topic annotations supply
context. From the representation page, compare the same source across Stages
1–5.

## Inspect regulatory evidence

```cypher
MATCH (anchor)-[:ABOUT_TOPIC]->(topic:Topic)
MATCH (anchor)-[:SUPPORTED_BY]->(block:Block)
WHERE anchor:Proposal OR anchor:FeedbackRequest
RETURN labels(anchor)[0] AS anchor_type,
       anchor.label AS anchor,
       topic.label AS topic,
       left(block.plain_text, 300) AS evidence,
       block.block_id AS block
ORDER BY topic, anchor
```

## Inspect exact backward references

Stage 4 connects language in a comment to a precise regulatory-action block:

```cypher
MATCH (source:Block)-[:HAS_EXACT_REFERENCE]->
  (reference:ExactReference)-[target:PRIMARY_TARGET]->(regulation:Block)
RETURN source.document_id AS comment_id,
       left(source.plain_text, 250) AS comment_passage,
       left(regulation.plain_text, 250) AS regulatory_passage,
       target.retrieval_score AS retrieval_score,
       source.browser_url AS open_comment
ORDER BY retrieval_score DESC
LIMIT 100
```

## Inspect citations

```cypher
MATCH (block:Block)-[:HAS_CITATION]->
  (occurrence:CitationOccurrence)-[:CITES]->(authority:Authority)
RETURN block.document_id AS document_id,
       authority.stable_id AS authority,
       authority.citation_family AS family,
       count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 100
```

## Shut down or rebuild

Stop Neo4j while retaining its local volume:

```shell
docker compose down
```

Delete only this Compose project's Neo4j volume and rebuild from the bundle:

```shell
docker compose down -v
docker compose up -d neo4j
```

`down -v` permanently removes the local projection. The file-backed graph
bundle and Markdown database remain authoritative.
