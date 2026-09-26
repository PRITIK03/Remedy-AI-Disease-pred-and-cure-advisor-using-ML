"""Medical Report and Report Extraction ORM models (Phase 7).

Stores report metadata, storage references, SHA-256 hashes, status, and
extracted structured metrics for cardiovascular assessments.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.assessment import Assessment


class ReportStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MedicalReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "medical_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status_enum", native_enum=False),
        nullable=False,
        default=ReportStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    extractions: Mapped[list[ReportExtraction]] = relationship(
        "ReportExtraction", back_populates="report", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[Assessment]] = relationship(
        "Assessment", back_populates="report"
    )

    __table_args__ = (
        Index("ix_medical_reports_user_created", "user_id", "created_at"),
    )


class ReportExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "report_extractions"

    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medical_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    extraction_model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Extracted 13 metrics (nullable values when missing in document)
    extracted_features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Per-field confidence scores (0.0 to 1.0)
    confidences: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    # Per-field evidence quotes or notes from document
    evidence: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    # Extraction notes/summary from LLM
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    report: Mapped[MedicalReport] = relationship("MedicalReport", back_populates="extractions")
