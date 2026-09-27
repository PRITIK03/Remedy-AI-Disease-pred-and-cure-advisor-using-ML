"""auth + assessment ownership

Revision ID: c3f8a1d20b47
Revises: dfadb23ef33c
Create Date: 2026-09-26

Phase 6:
- users: add password_hash (NULLable — legacy dev rows stay unable to log in;
  no invented passwords) and role (default 'user').
- assessments: add user_id (NULLable during transition; new assessments are
  always created with the authenticated owner) + index for ownership queries.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a1d20b47"
down_revision: str | None = "dfadb23ef33c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.add_column("assessments", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_assessments_user_id", "assessments", ["user_id"], unique=False
    )
    op.create_foreign_key(
        "fk_assessments_user_id_users",
        "assessments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_assessments_user_id_users", "assessments", type_="foreignkey")
    op.drop_index("ix_assessments_user_id", table_name="assessments")
    op.drop_column("assessments", "user_id")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
