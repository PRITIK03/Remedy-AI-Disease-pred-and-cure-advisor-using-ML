"""FastAPI auth dependencies (Phase 6).

- get_current_user: resolves the session cookie → Redis session → DB user.
  Missing/invalid cookie is an ANONYMOUS request (does NOT fail closed) so
  public endpoints keep working; protected endpoints use
  require_authenticated_user, which rejects anonymous requests.
- CSRF: unsafe methods (POST/PUT/PATCH/DELETE) must present the signed CSRF
  cookie value in the X-CSRF-Token header (double-submit + HMAC).
- Authorization is ALWAYS server-side here; the frontend hiding buttons is
  convenience, not protection.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import verify_csrf_token
from backend.app.db.models import User, UserRole
from backend.app.services.session_service import SessionService

from backend.app.dependencies import DbSessionDep, RedisServiceDep

CSRF_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def get_session_service(request: Request) -> SessionService:
    redis_service = getattr(request.app.state, "redis_service", None)
    settings = get_settings()
    return SessionService(redis_service, settings.session_ttl_seconds)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def _extract_session_id(request: Request) -> str | None:
    cookie_name = get_settings().session_cookie_name_resolved
    return request.cookies.get(cookie_name)


async def enforce_csrf(request: Request) -> None:
    """Double-submit CSRF check for unsafe methods; GET/HEAD/OPTIONS exempt."""
    if request.method not in CSRF_UNSAFE_METHODS:
        return
    settings = get_settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if (
        not cookie_token
        or not header_token
        or cookie_token != header_token  # double-submit equality
        or not verify_csrf_token(settings, header_token)  # + HMAC & expiry
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Refresh the page and try again.",
        )


async def get_current_user(
    request: Request,
    db: DbSessionDep,
    session_service: SessionServiceDep,
) -> User | None:
    """Resolve the current user, or None for anonymous/invalid sessions."""
    session_id = _extract_session_id(request)
    if not session_id:
        return None
    record = await session_service.get(session_id)
    if record is None:
        return None
    user = db.get(User, record.get("user_id"))
    if user is None or not user.is_active:
        return None
    request.state.user_id = str(user.id)
    return user


def require_authenticated_user(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Reject anonymous requests (401). CSRF is enforced at the router level."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


CurrentUserDep = Annotated[User, Depends(require_authenticated_user)]


def _role_hierarchy(user: User) -> set[UserRole]:
    roles = {UserRole.user}
    if user.role in (UserRole.reviewer, UserRole.admin):
        roles.add(UserRole.reviewer)
    if user.role == UserRole.admin:
        roles.add(UserRole.admin)
    return roles


def require_role(*required: UserRole):
    """Dependency factory: demand one of the given roles (403 otherwise)."""

    async def _dependency(user: CurrentUserDep) -> User:
        if not _role_hierarchy(user).intersection(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return user

    return _dependency


ReviewerOrAdminDep = Annotated[
    User, Depends(require_role(UserRole.reviewer, UserRole.admin))
]
