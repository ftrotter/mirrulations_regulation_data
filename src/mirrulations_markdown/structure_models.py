"""Strict configuration and annotation models for structure discovery."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class PassageEnrichment(BaseModel):
    """Strict response for one source passage."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    backward_references: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def validate_summary_sentence(cls, value):
        normalized_value = value.strip()
        if normalized_value.count(".") + normalized_value.count("!") + normalized_value.count("?") < 1:
            raise ValueError("structure_models.py Error: summary must be a complete sentence")
        return normalized_value

    @field_validator("backward_references")
    @classmethod
    def validate_backward_references(cls, values):
        normalized_values = []
        for value in values:
            normalized_value = value.strip()
            if not normalized_value.startswith("Look for "):
                normalized_value = "Look for " + normalized_value[:1].lower() + normalized_value[1:]
            if normalized_value[-1:] not in {".", "!", "?"}:
                raise ValueError(
                    "structure_models.py Error: backward references must be complete sentences"
                )
            normalized_values.append(normalized_value)
        return normalized_values


class DocumentEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    page_count: int | None
    page_count_method: str
    character_count: int
    maximum_comment_pages: int | None
    exclusion_reason: str | None = None