"""Security primitives — passwords, sessions, CSRF (Phase 6).

Design decisions (see docs/auth-security.md):

- Passwords: Argon2id via pwdlib (the currently recommended FastAPI/Python
  password-hashing library). Plaintext is never stored; hashes are never
  returned through the API or logged.
- Sessions: opaque 256-bit random session ids. Redis is the single store of
  truth with a TTL. The cookie carries ONLY the opaque id (HttpOnly) — never
  user ids, roles, passwords, or any health information.
- CSRF: signed double-submit token. Token = HMAC(secret, random || expires).
  The readable token goes to the client in a JS-readable cookie; the server
  requires the same value in the X-CSRF-Token header for unsafe methods and
  verifies the HMAC + expiry. A cross-site attacker can read neither the
  HttpOnly session cookie nor (without a same-origin XSS) craft a valid
  HMAC-signed token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from pwdlib import PasswordHash

# ---------------------------------------------------------------------------
# Passwords (Argon2id)
# ---------------------------------------------------------------------------

_password_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    """Hash a password with Argon2id. Never log the input or the hash."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification. Invalid/malformed hashes verify False."""
    if not password_hash:
        return False
    try:
        return _password_hasher.verify(password, password_hash)
    except Exception:  # noqa: BLE001 - malformed hash must not leak via 500
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses outdated parameters (for login rehash)."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Session ids (opaque, high entropy)
# ---------------------------------------------------------------------------


def generate_session_id() -> str:
    """Opaque 256-bit session id. Carries no meaning — only Redis knows it."""
    return secrets.token_urlsafe(32)


def hash_session_id(session_id: str) -> str:
    """Redis stores a SHA-256 of the id, not the raw value.

    A Redis dump alone then cannot be replayed as a valid session cookie.
    """
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CSRF (HMAC-signed double-submit)
# ---------------------------------------------------------------------------

CSRF_TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12h; re-issued with each session


def _csrf_secret(settings) -> bytes:
    """CSRF signing secret.

    DEV/TEST fallback: derived from the database URL so it is deterministic
    but never hardcoded. PRODUCTION: SECRET_KEY is REQUIRED (config refuses
    to serve with the fallback in production).
    """
    secret = getattr(settings, "secret_key", "")
    if not secret:
        if settings.is_production:
            raise RuntimeError(
                "SECRET_KEY is required when APP_ENV=production"
            )
        secret = "dev-csrf:" + settings.database_url
    return secret.encode("utf-8")


def generate_csrf_token(settings) -> str:
    """Create a signed CSRF token: nonce.expiry.signature (urlsafe)."""
    nonce = secrets.token_urlsafe(24)
    expires = str(int(time.time()) + CSRF_TOKEN_TTL_SECONDS)
    payload = f"{nonce}.{expires}"
    sig = hmac.new(
        _csrf_secret(settings), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{sig}"


def verify_csrf_token(settings, token: str) -> bool:
    """Verify HMAC signature + expiry. Constant-time comparison."""
    if not token or token.count(".") != 2:
        return False
    try:
        nonce, expires_str, signature = token.split(".")
        payload = f"{nonce}.{expires_str}"
        expected = hmac.new(
            _csrf_secret(settings), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        if int(expires_str) < int(time.time()):
            return False
        return True
    except (ValueError, TypeError):
        return False
