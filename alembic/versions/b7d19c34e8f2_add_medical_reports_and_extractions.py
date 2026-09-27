"""add medical reports and report extractions tables

Revision ID: b7d19c34e8f2
Revises: c3f8a1d20b47
Create Date: 2026-09-26

Phase 7:
- medical_reports: uploaded report metadata, storage reference, sha256, status.
- report_extractions: structured metrics extracted from document with model, confidence & evidence.
- assessments: add source ("manual" | "report") and report_id foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d19c34e8f2"
down_revision: str | None = "c3f8a1d20b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None



def upgrade() -> None:
    # 1. Create medical_reports table
    op.create_table(
        "medical_reports",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_medical_reports_user_id", "medical_reports", ["user_id"])
    op.create_index("ix_medical_reports_file_hash", "medical_reports", ["file_hash"])
    op.create_index("ix_medical_reports_status", "medical_reports", ["status"])
    op.create_index("ix_medical_reports_user_created", "medical_reports", ["user_id", "created_at"])

    # 2. Create report_extractions table
    op.create_table(
        "report_extractions",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("extracted_features", sa.JSON(), nullable=False),
        sa.Column("confidences", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["medical_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_extractions_report_id", "report_extractions", ["report_id"])

    # 3. Add source and report_id columns to assessments table
    op.add_column(
        "assessments",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "assessments",
        sa.Column("report_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_assessments_report_id", "assessments", ["report_id"])
    op.create_foreign_key(
        "fk_assessments_report_id_medical_reports",
        "assessments",
        "medical_reports",
        ["report_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_assessments_report_id_medical_reports", "assessments", type_="foreignkey")
    op.drop_index("ix_assessments_report_id", table_name="assessments")
    op.drop_column("assessments", "report_id")
    op.drop_column("assessments", "source")

    op.drop_index("ix_report_extractions_report_id", table_name="report_extractions")
    op.drop_table("report_extractions")

    op.drop_index("ix_medical_reports_user_created", table_name="medical_reports")
    op.drop_index("ix_medical_reports_status", table_name="medical_reports")
    op.drop_index("ix_medical_reports_file_hash", table_name="medical_reports")
    op.drop_index("ix_medical_reports_user_id", table_name="medical_reports")
    op.drop_table("medical_reports")
