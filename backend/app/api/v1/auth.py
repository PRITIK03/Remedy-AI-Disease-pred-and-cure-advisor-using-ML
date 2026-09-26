"""Auth API endpoints (/api/v1/auth) — Phase 6.

Security invariants:
- The session cookie is HttpOnly; responses NEVER include the session id.
- Login failures are generic (anti-enumeration) and rate limited.
- All auth responses are no-store (never cached).
- On login/register a fresh CSRF token is minted and set as a JS-readable
  cookie; unsafe requests must echo it in X-CSRF-Token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.app.core.config import get_settings
from backend.app.core.security import generate_csrf_token
from backend.app.db.models import User
from backend.app.dependencies import DbSessionDep, RedisServiceDep
from backend.app.dependencies_auth import (
    CurrentUserDep,
    SessionServiceDep,
    enforce_csrf,
)
from backend.app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RegisterRequest,
)
from backend.app.services import auth_service
from backend.app.services.rate_limit_service import (
    RateLimitExceededError,
    RateLimiter,
)
from backend.app.services.session_service import (
    SessionStoreUnavailableError,
    csrf_cookie_kwargs,
    session_cookie_kwargs,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    # CSRF double-submit on EVERY unsafe method here — including register and
    # login (prevents login-CSRF). The frontend fetches GET /auth/csrf first
    # to obtain the cookie, then echoes it in X-CSRF-Token.
    dependencies=[Depends(enforce_csrf)],
)

NO_STORE = {"Cache-Control": "no-store"}


def _set_auth_cookies(response: Response, request: Request, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        value=session_id, **session_cookie_kwargs(settings)
    )
    response.set_cookie(
        value=generate_csrf_token(settings), **csrf_cookie_kwargs(settings)
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name_resolved,
        path="/",
        domain=settings.cookie_domain or None,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=settings.cookie_domain or None,
    )


def _client_identifier(request: Request) -> str:
    """Stable-ish rate-limit identity without logging PII: client IP hash."""
    import hashlib

    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


async def _check_rate_limit(
    request: Request, redis_service, *, bucket: str, limit: int
) -> None:
    limiter = RateLimiter(redis_service)
    try:
        await limiter.check(
            bucket=bucket,
            identifier=_client_identifier(request),
            limit=limit,
            window_seconds=3600,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except SessionStoreUnavailableError as exc:
        # Fail closed: no Redis → no auth attempts.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc


async def _create_session_or_503(session_service, user_id: str, response: Response, request: Request) -> None:
    """Create the session + cookies; Redis outage maps to 503 (fail closed)."""
    try:
        session_id, _ = await session_service.create(user_id)
    except SessionStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc
    _set_auth_cookies(response, request, session_id)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account (rate limited)",
)
async def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    db: DbSessionDep,
    redis_service: RedisServiceDep,
    session_service: SessionServiceDep,
):
    await _check_rate_limit(
        request,
        redis_service,
        bucket="register",
        limit=get_settings().auth_rate_limit_register_per_hour,
    )
    try:
        user = auth_service.register_user(
            db,
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password,
        )
    except auth_service.DuplicateEmailError as exc:
        # Deliberately vague: no confirmation of which detail conflicted.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create account with these details.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create account with these details.",
        ) from exc

    await _create_session_or_503(session_service, str(user.id), response, request)
    return AuthResponse(user=user.to_public())


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in (rate limited, generic failures)",
)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: DbSessionDep,
    redis_service: RedisServiceDep,
    session_service: SessionServiceDep,
):
    await _check_rate_limit(
        request,
        redis_service,
        bucket="login",
        limit=get_settings().auth_rate_limit_login_per_hour,
    )
    try:
        user = auth_service.authenticate(
            db, email=payload.email, password=payload.password
        )
    except auth_service.InvalidCredentialsError as exc:
        # Identical status/body for every failure reason (anti-enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_service.GENERIC_LOGIN_FAILED,
        ) from exc
    except SessionStoreUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        )

    try:
        session_id, _ = await session_service.create(str(user.id))
    except SessionStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc
    _set_auth_cookies(response, request, session_id)
    return AuthResponse(user=user.to_public())


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Invalidate the current session server-side",
)
async def logout(
    response: Response,
    request: Request,
    user: CurrentUserDep,  # a valid session is required to log out
    session_service: SessionServiceDep,
):
    session_id = request.cookies.get(get_settings().session_cookie_name_resolved)
    if session_id:
        await session_service.delete(session_id)
    _clear_auth_cookies(response)
    return LogoutResponse(logged_out=True)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current authenticated user",
)
async def me(user: CurrentUserDep):
    return user.to_public()


@router.get(
    "/csrf",
    summary="Mint a CSRF token cookie (public; call before first unsafe request)",
)
async def get_csrf_token(
    response: Response,
):
    """Issue a fresh CSRF cookie. Public by design: a pre-auth visitor needs
    it to POST /login or /register. It grants no privileges by itself."""
    settings = get_settings()
    response.set_cookie(
        value=generate_csrf_token(settings), **csrf_cookie_kwargs(settings)
    )
    return {"csrf_header": settings.csrf_header_name}
