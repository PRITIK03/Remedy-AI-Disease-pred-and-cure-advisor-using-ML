"""Assessment ORM model — one row per model inference (no real patient data)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Assessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    # --- ML inputs (the 13 legacy features, explicit columns, NOT a blob) --- #
    age: Mapped[int] = mapped_column(nullable=False, index=True)
    sex: Mapped[int] = mapped_column(nullable=False)
    cp: Mapped[int] = mapped_column(nullable=False)
    trestbps: Mapped[int] = mapped_column(nullable=False)
    chol: Mapped[int] = mapped_column(nullable=False)
    fbs: Mapped[int] = mapped_column(nullable=False)
    restecg: Mapped[int] = mapped_column(nullable=False)
    thalach: Mapped[int] = mapped_column(nullable=False)
    exang: Mapped[int] = mapped_column(nullable=False)
    oldpeak: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    slope: Mapped[int] = mapped_column(nullable=False)
    ca: Mapped[int] = mapped_column(nullable=False)
    thal: Mapped[int] = mapped_column(nullable=False)

    # --- Prediction result --------------------------------------------------- #
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    predicted_disease: Mapped[bool] = mapped_column(nullable=False)
    disease_probability: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    selected_model: Mapped[str] = mapped_column(String(64), nullable=False)

    # Supplemental, non-sensitive metadata (justified: keeps explainability
    # payloads out of core columns without schema churn in this phase).
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_assessments_created_at", "created_at"),
        Index("ix_assessments_model_version", "model_version"),
        Index("ix_assessments_predicted_disease", "predicted_disease"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Assessment id={self.id} model_version={self.model_version} "
            f"probability={self.disease_probability}>"
        )
