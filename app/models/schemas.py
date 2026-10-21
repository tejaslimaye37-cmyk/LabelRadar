"""API Request and Response schemas for LabelRadar endpoints."""


from pydantic import BaseModel, Field

from app.models.graph import ChangeType

# --- Ingest Schemas ---

class IngestRequest(BaseModel):
    """Payload to trigger ingestion of drug label versions from openFDA."""

    drug_name: str = Field(
        ...,
        description="Brand name, generic name, or substance name (e.g. Lipitor, semaglutide, acetaminophen)",
        examples=["Lipitor"],
    )
    spl_set_id: str | None = Field(
        default=None,
        description="Optional specific SPL Set ID GUID if known. Leave null or empty to search by drug name.",
        examples=[None],
    )
    max_versions: int = Field(
        20,
        ge=1,
        le=100,
        description="Max label versions to fetch and diff",
        examples=[10],
    )


class VersionSummary(BaseModel):
    """Summary of an ingested label version."""

    version_id: str
    version_number: str
    effective_date: str | None = None
    section_count: int = 0


class IngestResponse(BaseModel):
    """Result of drug label ingestion."""

    success: bool = True
    drug_name: str
    spl_set_id: str | None = None
    versions_ingested: int
    sections_created: int
    diffs_computed: int
    versions: list[VersionSummary] = Field(default_factory=list)
    message: str = "Ingestion completed successfully."


# --- Changes Schemas ---

class SectionChangeDetail(BaseModel):
    """Detailed diff for a specific section change."""

    section_name: str
    change_type: ChangeType
    diff: str
    added_lines: int
    removed_lines: int
    similarity_ratio: float
    summary: str | None = None


class VersionTransition(BaseModel):
    """Represents changes occurring between two consecutive versions."""

    from_version_id: str
    to_version_id: str
    from_version_number: str
    to_version_number: str
    effective_date: str | None = None
    changes_count: int
    changes: list[SectionChangeDetail] = Field(default_factory=list)


class DrugChangesTimelineResponse(BaseModel):
    """Structured timeline of label changes for a drug."""

    drug_name: str
    spl_set_id: str | None = None
    total_versions: int
    total_transitions: int
    total_changes: int
    timeline: list[VersionTransition] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health status response."""

    status: str = "healthy"
    app: str = "LabelRadar"
    environment: str
    databases: dict[str, str] = Field(default_factory=dict)
