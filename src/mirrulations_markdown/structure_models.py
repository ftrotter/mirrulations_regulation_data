"""Strict configuration and annotation models for structure discovery."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SUPPORTED_PROVIDERS = ("openai", "anthropic", "google")


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str = Field(min_length=1)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value):
        normalized_value = value.strip().lower()
        if normalized_value not in SUPPORTED_PROVIDERS:
            raise ValueError(
                "structure_models.py Error: provider must be openai, anthropic, or google"
            )
        return normalized_value

    @property
    def model_key(self):
        return f"{self.provider}/{self.model}"


class StructureConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_model: ModelSpec
    reference_model: ModelSpec
    summary_mode: str = "sections"
    max_comment_pages: int = Field(default=50, ge=1)
    characters_per_estimated_page: int = Field(default=3000, ge=1)
    summary_prompt_version: int = Field(default=1, ge=1)
    reference_prompt_version: int = Field(default=1, ge=1)

    @field_validator("reference_model")
    @classmethod
    def validate_shared_model(cls, value, info):
        summary_model = info.data.get("summary_model")
        if summary_model is not None and value != summary_model:
            raise ValueError(
                "structure_models.py Error: this increment uses one typed call; "
                "summary_model and reference_model must match"
            )
        return value

    @field_validator("summary_mode")
    @classmethod
    def validate_summary_mode(cls, value):
        if value not in {"sections", "deep"}:
            raise ValueError("structure_models.py Error: summary_mode must be sections or deep")
        return value


class BackwardReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_key: str = Field(min_length=1)
    search_description: str = Field(min_length=1)

    @field_validator("search_description")
    @classmethod
    def normalize_description(cls, value):
        normalized_value = value.strip()
        if normalized_value.lower().startswith("look for "):
            normalized_value = normalized_value[9:].strip()
        if normalized_value[-1:] in {".", "!", "?"}:
            normalized_value = normalized_value[:-1].strip()
        vague_scope_patterns = (
            r"\ba proposed rule\b",
            r"\bthe proposed rule\b",
            r"\ba proposed rule provision\b",
        )
        if any(
            re.search(pattern, normalized_value, flags=re.IGNORECASE)
            for pattern in vague_scope_patterns
        ):
            raise ValueError(
                "structure_models.py Error: search_description must describe "
                "the sought passage without a vague target scope"
            )
        return normalized_value[:1].lower() + normalized_value[1:]


class PassageEnrichment(BaseModel):
    """Strict response for one source passage."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    backward_references: list[BackwardReference] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def validate_summary_sentence(cls, value):
        normalized_value = value.strip()
        if normalized_value.count(".") + normalized_value.count("!") + normalized_value.count("?") < 1:
            raise ValueError("structure_models.py Error: summary must be a complete sentence")
        return normalized_value


class SegmentBlockEnrichment(BaseModel):
    """Reference findings for one owned block inside a contextual segment."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    backward_references: list[BackwardReference] = Field(default_factory=list)


class SegmentEnrichment(BaseModel):
    """Strict response for one coherent document segment."""

    model_config = ConfigDict(extra="forbid")

    section_summary: str | None = None
    block_results: list[SegmentBlockEnrichment]

    @field_validator("section_summary")
    @classmethod
    def validate_optional_summary(cls, value):
        if value is None:
            return value
        normalized_value = value.strip()
        if normalized_value.count(".") + normalized_value.count("!") + normalized_value.count("?") < 1:
            raise ValueError(
                "structure_models.py Error: section summary must be a complete sentence"
            )
        return normalized_value


class ReferenceLinkAssessment(BaseModel):
    """Strict assessment of retrieved regulatory-action candidate blocks."""

    model_config = ConfigDict(extra="forbid")

    target_block_ids: list[str] = Field(default_factory=list)
    confidence: str
    rationale: str = Field(min_length=1)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value):
        normalized_value = value.strip().lower()
        if normalized_value not in {"high", "medium", "low", "no-match"}:
            raise ValueError(
                "structure_models.py Error: linker confidence must be high, "
                "medium, low, or no-match"
            )
        return normalized_value

    @model_validator(mode="after")
    def validate_match_consistency(self):
        if not self.target_block_ids and self.confidence != "no-match":
            raise ValueError(
                "structure_models.py Error: empty linker targets require no-match confidence"
            )
        if self.target_block_ids and self.confidence == "no-match":
            raise ValueError(
                "structure_models.py Error: selected linker targets cannot use no-match confidence"
            )
        return self

class DocumentEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    page_count: int | None
    page_count_method: str
    character_count: int
    maximum_comment_pages: int | None
    exclusion_reason: str | None = None