"""Strict file-backed models for the MVP topic and Neo4j graph."""

from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONCEPT_ID_PATTERN = re.compile(
    r"^(?:topic|issue|proposal|requirement|feedback-request|run)-"
    r"[0-9A-HJKMNP-TV-Z]{26}$"
)
GRAPH_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
REVIEW_STATUSES = ("proposed", "accepted", "rejected")


class StrictGraphModel(BaseModel):
    """Base model that rejects misspelled or unplanned fields."""

    model_config = ConfigDict(extra="forbid")


class EvidenceReference(StrictGraphModel):
    document_version_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    matched_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.end <= self.start:
            raise ValueError(
                "graph_models.py Error: evidence end must be greater than start"
            )
        return self


class TopicRecord(StrictGraphModel):
    topic_id: str
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    origin: Literal["agency-derived", "comment-derived", "human-authored"]
    review_status: Literal["proposed", "accepted", "rejected"]
    parent_topic_ids: list[str] = Field(default_factory=list)

    @field_validator("topic_id")
    @classmethod
    def validate_topic_id(cls, value):
        if not value.startswith("topic-") or not CONCEPT_ID_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: topic_id must be a topic ULID")
        return value

    @field_validator("parent_topic_ids")
    @classmethod
    def validate_parent_topic_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("graph_models.py Error: parent topic IDs must be unique")
        for value in values:
            if not value.startswith("topic-") or not CONCEPT_ID_PATTERN.fullmatch(value):
                raise ValueError(
                    "graph_models.py Error: parent_topic_ids must contain topic ULIDs"
                )
        return values

    @model_validator(mode="after")
    def validate_not_own_parent(self):
        if self.topic_id in self.parent_topic_ids:
            raise ValueError("graph_models.py Error: a topic cannot be its own parent")
        return self


class TopicAssignmentRecord(StrictGraphModel):
    schema_version: Literal[1] = 1
    assignment_id: str = Field(pattern=r"^topic-assignment-[a-f0-9]{64}$")
    document_version_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    topic_id: str
    assignment_method: Literal["agency-anchor", "corex", "llm", "human"]
    analysis_run_id: str
    score: float | None = None
    review_status: Literal["proposed", "accepted", "rejected"]
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    review_rationale: str | None = None

    @field_validator("topic_id")
    @classmethod
    def validate_topic_id(cls, value):
        if not value.startswith("topic-") or not CONCEPT_ID_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: topic_id must be a topic ULID")
        return value

    @field_validator("analysis_run_id")
    @classmethod
    def validate_run_id(cls, value):
        if not value.startswith("run-") or not CONCEPT_ID_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: analysis_run_id must be a run ULID")
        return value

    @model_validator(mode="after")
    def validate_review_metadata(self):
        review_values = (self.reviewer, self.reviewed_at, self.review_rationale)
        if self.review_status in {"accepted", "rejected"} and any(
            value is None for value in review_values
        ):
            raise ValueError(
                "graph_models.py Error: reviewed assignments require reviewer, "
                "reviewed_at, and review_rationale"
            )
        return self


class PipelineRunRecord(StrictGraphModel):
    run_id: str
    run_type: str = Field(min_length=1)
    status: Literal["complete", "partial", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    input_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    code_commit: str = Field(min_length=1)
    configuration_version: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    random_seed: int | None = None

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value):
        if not value.startswith("run-") or not CONCEPT_ID_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: run_id must be a run ULID")
        return value


class GraphNode(StrictGraphModel):
    label: str
    stable_id: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value):
        if not GRAPH_NAME_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: invalid Neo4j node label")
        return value


class GraphRelationship(StrictGraphModel):
    relationship_type: str
    source_label: str
    source_id: str = Field(min_length=1)
    target_label: str
    target_id: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, value):
        if not re.fullmatch(r"^[A-Z][A-Z0-9_]*$", value):
            raise ValueError("graph_models.py Error: invalid Neo4j relationship type")
        return value

    @field_validator("source_label", "target_label")
    @classmethod
    def validate_endpoint_label(cls, value):
        if not GRAPH_NAME_PATTERN.fullmatch(value):
            raise ValueError("graph_models.py Error: invalid Neo4j endpoint label")
        return value


class GraphBundle(StrictGraphModel):
    schema_version: Literal[1] = 1
    generated_by_run_id: str
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]

    @model_validator(mode="after")
    def validate_graph_references(self):
        node_keys = [(node.label, node.stable_id) for node in self.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("graph_models.py Error: graph node identities must be unique")
        available_nodes = set(node_keys)
        relationship_keys = []
        for relationship in self.relationships:
            source_key = (relationship.source_label, relationship.source_id)
            target_key = (relationship.target_label, relationship.target_id)
            missing_endpoints = [
                endpoint for endpoint in (source_key, target_key)
                if endpoint not in available_nodes
            ]
            if missing_endpoints:
                raise ValueError(
                    "graph_models.py Error: relationship endpoint does not exist: "
                    f"{relationship.relationship_type} missing {missing_endpoints}"
                )
            relationship_keys.append((
                relationship.relationship_type,
                relationship.source_label,
                relationship.source_id,
                relationship.target_label,
                relationship.target_id,
            ))
        if len(relationship_keys) != len(set(relationship_keys)):
            raise ValueError(
                "graph_models.py Error: graph relationships must be unique"
            )
        return self