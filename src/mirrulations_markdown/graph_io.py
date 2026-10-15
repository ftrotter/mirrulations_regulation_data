"""Deterministic graph-bundle serialization and Neo4j import."""

import json
from itertools import groupby
from pathlib import Path

from .graph_models import GraphBundle


def load_graph_bundle(*, bundle_path):
    try:
        bundle_data = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"graph_io.py Error: cannot read graph bundle: {error}") from error
    return GraphBundle.model_validate(bundle_data)


def write_graph_bundle(*, bundle, bundle_path):
    validated_bundle = GraphBundle.model_validate(bundle)
    bundle_data = validated_bundle.model_dump(mode="json")
    bundle_data["nodes"] = sorted(
        bundle_data["nodes"], key=lambda node: (node["label"], node["stable_id"])
    )
    bundle_data["relationships"] = sorted(
        bundle_data["relationships"],
        key=lambda relationship: (
            relationship["relationship_type"],
            relationship["source_label"],
            relationship["source_id"],
            relationship["target_label"],
            relationship["target_id"],
        ),
    )
    selected_path = Path(bundle_path)
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = selected_path.with_suffix(selected_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(bundle_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(selected_path)


def _batches(*, values, batch_size):
    for start in range(0, len(values), batch_size):
        yield values[start:start + batch_size]


def import_graph_bundle(*, bundle, driver, batch_size=1000):
    """Idempotently merge a validated bundle through an active Neo4j driver."""
    if batch_size < 1:
        raise ValueError("graph_io.py Error: batch_size must be positive")
    validated_bundle = GraphBundle.model_validate(bundle)
    with driver.session() as session:
        for node_label in sorted({node.label for node in validated_bundle.nodes}):
            session.run(
                f"CREATE CONSTRAINT IF NOT EXISTS FOR "
                f"(graph_node:{node_label}) REQUIRE graph_node.stable_id IS UNIQUE"
            )
        sorted_nodes = sorted(
            validated_bundle.nodes, key=lambda item: (item.label, item.stable_id)
        )
        for node_label, grouped_nodes in groupby(
            sorted_nodes, key=lambda item: item.label
        ):
            node_rows = [
                {"stable_id": node.stable_id, **node.properties}
                for node in grouped_nodes
            ]
            for batch in _batches(values=node_rows, batch_size=batch_size):
                session.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (graph_node:{node_label} {{stable_id: row.stable_id}}) "
                    "SET graph_node += row",
                    rows=batch,
                )
        sorted_relationships = sorted(
            validated_bundle.relationships,
            key=lambda item: (
                item.relationship_type, item.source_label, item.target_label,
                item.source_id, item.target_id,
            ),
        )
        relationship_group_key = lambda item: (
            item.relationship_type, item.source_label, item.target_label
        )
        for group_key, grouped_relationships in groupby(
            sorted_relationships, key=relationship_group_key
        ):
            relationship_type, source_label, target_label = group_key
            relationship_rows = [
                {
                    "source_id": relationship.source_id,
                    "target_id": relationship.target_id,
                    "properties": relationship.properties,
                }
                for relationship in grouped_relationships
            ]
            for batch in _batches(values=relationship_rows, batch_size=batch_size):
                session.run(
                    "UNWIND $rows AS row "
                    f"MATCH (source_node:{source_label} "
                    "{stable_id: row.source_id}) "
                    f"MATCH (target_node:{target_label} "
                    "{stable_id: row.target_id}) "
                    f"MERGE (source_node)-[graph_relationship:"
                    f"{relationship_type}]->(target_node) "
                    "SET graph_relationship += row.properties",
                    rows=batch,
                )