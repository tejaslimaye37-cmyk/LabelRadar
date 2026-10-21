"""Pydantic and Cypher models representing the Neo4j graph entities."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    """Classification of change between two consecutive section versions."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class DrugNode(BaseModel):
    """(:Drug) node representation."""

    name: str = Field(description="Normalized uppercase drug name / identifier")
    brand_name: str | None = None
    generic_name: str | None = None
    spl_set_id: str | None = None


class LabelVersionNode(BaseModel):
    """(:LabelVersion) node representation."""

    version_id: str = Field(description="Unique version identifier (e.g. spl_id or set_id:version)")
    version_number: str = "1"
    effective_date: str | None = None  # YYYY-MM-DD
    spl_set_id: str | None = None


class SectionNode(BaseModel):
    """(:Section) node representation."""

    section_id: str = Field(description="Unique section identifier (e.g. version_id:section_name)")
    section_name: str
    version_id: str
    text: str = ""
    text_hash: str = ""
    char_count: int = 0
    status: str = "active"  # active, removed, absent


class ChangedToEdge(BaseModel):
    """(:Section)-[:CHANGED_TO]->(:Section) edge properties."""

    change_type: ChangeType
    section_name: str
    diff: str = ""
    added_lines: int = 0
    removed_lines: int = 0
    similarity_ratio: float = 1.0
    summary: str | None = None
    from_version_id: str | None = None
    to_version_id: str | None = None
