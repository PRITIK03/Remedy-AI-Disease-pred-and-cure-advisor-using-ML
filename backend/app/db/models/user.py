"""User ORM model — authentication fields (Phase 6).

Roles are groundwork for the future LangGraph human-review workflow; no
reviewer UI exists yet. Existing pre-auth dev rows keep NULL password_hash
and are simply unable to log in until they register again (documented,
dev-stage acceptable).
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    user = "user"
    reviewer = "reviewer"
    admin = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Authentication (Phase 6) ------------------------------------------- #
    # Argon2id hash; NULL for legacy pre-auth development rows (they cannot
    # authenticate until they register credentials — no invented passwords).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        default=UserRole.user,
        nullable=False,
    )

    def to_public(self) -> dict:
        """Safe serialization — NEVER includes the password hash."""
        return {
            "id": str(self.id),
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role.value if isinstance(self.role, UserRole) else str(self.role),
            "is_active": self.is_active,
            "created_at": self.created_at,
        }
