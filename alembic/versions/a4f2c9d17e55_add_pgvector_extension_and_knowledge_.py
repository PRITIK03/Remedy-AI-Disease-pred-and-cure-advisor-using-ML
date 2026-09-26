"""add pgvector extension and knowledge base tables

Revision ID: a4f2c9d17e55
Revises: dfadb23ef33c
Create Date: 2026-09-26

pgvector note: the `vector` extension must be installed on the PostgreSQL
server BEFORE this migration runs (server-side binary + `CREATE EXTENSION`).
On Windows: compile from source with MSVC Build Tools, or use a
pgvector-enabled container image. This migration creates the extension
idempotently and adds knowledge_documents / knowledge_chunks.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a4f2c9d17e55"
down_revision: Union[str, None] = "b7d19c34e8f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default dimension for the initial deployment. Must match EMBEDDING_DIMENSION
# (and the chosen embedding model's output size). Changing the embedding model
# requires a NEW migration to ALTER the column type and full re-ingestion.
EMBEDDING_DIM = 1024


def upgrade() -> None:
    # Idempotent extension creation (requires the pgvector server binary).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_documents",
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("publication_date", sa.String(length=32), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("source_url", name=op.f("uq_knowledge_documents_source_url")),
    )
    op.create_index(
        op.f("ix_knowledge_documents_content_hash"),
        "knowledge_documents",
        ["content_hash"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_placeholder", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id", "content_hash", name="uq_knowledge_chunks_content"
        ),
    )
    # Swap the placeholder for a real fixed-dimension vector column.
    op.drop_column("knowledge_chunks", "embedding_placeholder")
    op.execute(
        f"ALTER TABLE knowledge_chunks ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
    )
    op.create_index(
        "ix_knowledge_chunks_document",
        "knowledge_chunks",
        ["document_id", "chunk_index"],
        unique=False,
    )
    # Exact (sequential-scan) cosine search at this scale; no ANN index yet.
    # (Add an HNSW/IVFFlat index only when the corpus grows large.)


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_document", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        op.f("ix_knowledge_documents_content_hash"), table_name="knowledge_documents"
    )
    op.drop_table("knowledge_documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
