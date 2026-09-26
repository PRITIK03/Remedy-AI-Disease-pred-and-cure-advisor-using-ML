"""Auth service — registration + login (Phase 6).

Anti-enumeration rules:
- Login ALWAYS returns the same generic failure for unknown email, legacy
  user without password, inactive user, and wrong password.
- A dummy Argon2 verification runs when the email is unknown so response
  timing cannot distinguish "no such user" from "wrong password".
- Duplicate registration is rejected with the same error shape regardless of
  which detail triggered it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger
from backend.app.core.security import hash_password, needs_rehash, verify_password
from backend.app.db.models import User, UserRole

logger = get_logger("backend.auth_service")

# Generic message for ANY login failure — never reveals which part failed.
GENERIC_LOGIN_FAILED = "Invalid email or password."

# Pre-computed dummy hash so the unknown-email path still burns ~Argon2 time.
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalization")


class DuplicateEmailError(RuntimeError):
    """Registration attempted with an email that already has credentials."""


class InvalidCredentialsError(RuntimeError):
    """Login failed (reason deliberately not exposed)."""


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id) -> User | None:
    return db.get(User, user_id)


def register_user(
    db: Session, *, email: str, display_name: str, password: str
) -> User:
    """Create a user with an Argon2id hash. Raises DuplicateEmailError."""
    existing = get_user_by_email(db, email)
    if existing is not None and existing.password_hash:
        raise DuplicateEmailError()

    password_hash = hash_password(password)
    if existing is not None:
        # Legacy pre-auth dev row: attach credentials instead of failing.
        existing.password_hash = password_hash
        if existing.display_name is None:
            existing.display_name = display_name
        logger.info("Legacy user attached credentials (no PII logged)")
        return existing

    user = User(
        email=email,
        display_name=display_name,
        password_hash=password_hash,
        role=UserRole.user,
        is_active=True,
    )
    db.add(user)
    db.flush()
    logger.info("User registered (no PII logged)")
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    """Verify credentials; raise InvalidCredentialsError on ANY failure."""
    user = get_user_by_email(db, email)

    if user is None:
        # Equalize timing: burn an Argon2 verification anyway.
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentialsError()

    if not user.password_hash:
        # Legacy row without credentials cannot log in (no invented secrets).
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentialsError()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()

    # Transparent upgrade if hashing parameters have since been raised.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user
