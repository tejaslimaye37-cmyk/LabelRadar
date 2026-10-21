"""SQLAlchemy models for PostgreSQL + pgvector persistence."""

import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback if pgvector is not imported during lightweight runs
    Vector = None  # type: ignore


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class DrugRecord(Base):
    """Database record for an ingested drug."""

    __tablename__ = "drugs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spl_set_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    versions: Mapped[list["LabelVersionRecord"]] = relationship(
        "LabelVersionRecord", back_populates="drug", cascade="all, delete-orphan"
    )


class LabelVersionRecord(Base):
    """Database record for a specific drug label version."""

    __tablename__ = "label_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drug_id: Mapped[int] = mapped_column(Integer, ForeignKey("drugs.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version_number: Mapped[str] = mapped_column(String(32), default="1")
    effective_date: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.utcnow
    )

    drug: Mapped["DrugRecord"] = relationship("DrugRecord", back_populates="versions")
    sections: Mapped[list["LabelSectionRecord"]] = relationship(
        "LabelSectionRecord", back_populates="version", cascade="all, delete-orphan"
    )


class LabelSectionRecord(Base):
    """Database record for an individual section within a label version."""

    __tablename__ = "label_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("label_versions.id", ondelete="CASCADE"), index=True
    )
    section_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.utcnow
    )

    # Embedding column using pgvector (1536 dim default)
    # Using conditional type to allow running even if pgvector extension is mocking
    if Vector is not None:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    version: Mapped["LabelVersionRecord"] = relationship("LabelVersionRecord", back_populates="sections")


class SectionDiffRecord(Base):
    """Database record for section diff between consecutive versions."""

    __tablename__ = "section_diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drug_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    from_version_id: Mapped[str] = mapped_column(String(128), index=True)
    to_version_id: Mapped[str] = mapped_column(String(128), index=True)
    section_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, default="")
    added_lines: Mapped[int] = mapped_column(Integer, default=0)
    removed_lines: Mapped[int] = mapped_column(Integer, default=0)
    similarity_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.utcnow
    )

    __table_args__ = (
        Index("ix_diff_drug_section", "drug_name", "section_name"),
    )
