# Authentication & Security (Phase 6 — as implemented)

This document describes the authentication, authorization, and hardening
added in Phase 6. It distinguishes **development** from **production**
behavior everywhere the two differ.

```text
Browser ── HttpOnly session cookie ──▶ FastAPI
                                        ├── CSRF check (unsafe methods)
                                        ├── session lookup (Redis, hashed key)
                                        ├── user load (PostgreSQL)
                                        └── authorization → endpoint
```

## Registration

- `POST /api/v1/auth/register` — email (validated + normalized via
  `email-validator`), display name, password (min 10 chars, max 128).
- Password confirmation is a frontend-only field; the API takes one password.
- Duplicate/unusable registrations return one generic 409
  ("Unable to create account with these details.").
- Legacy pre-auth dev rows (users without credentials) are upgraded in place
  on first registration of that email; no passwords are ever invented.

## Password hashing

- **Argon2id** via `pwdlib` (`PasswordHash.recommended()`), the currently
  recommended FastAPI/Python password-hashing library.
- Plaintext is never stored or logged; hashes are never returned by the API.
- On login, hashes using outdated parameters are transparently re-hashed
  (`check_needs_rehash`).
- Login runs a dummy Argon2 verification for unknown emails so response
  timing cannot reveal whether an account exists.

## Session lifecycle

- `POST /api/v1/auth/login` → server creates an **opaque 256-bit session id**
  (`secrets.token_urlsafe(32)`), stores `{user_id, created_at, expires_at}`
  in Redis under `session:{sha256(id)}` with a TTL, and sets the cookie.
- Redis is the single source of truth; expiry is the Redis TTL itself.
- `GET /api/v1/auth/me` → resolves cookie → Redis → PostgreSQL user.
- `POST /api/v1/auth/logout` → **deletes the server-side session**, then
  clears cookies. Clearing the browser cookie alone does NOT log out.
- Sessions are short-lived and configurable: `SESSION_TTL_SECONDS`
  (default 8h, validated to 1 min – 7 days).
- **Fail-closed:** if Redis is unavailable, login/register/logout and
  session lookup raise → 503. The API never degrades to an insecure mode.

## Cookie settings

| Cookie | Name (default) | HttpOnly | Secure | SameSite | Purpose |
|---|---|---|---|---|---|
| Session | `remedy_session` (or `__Host-remedy_session`) | yes | env `COOKIE_SECURE` | Lax | opaque session id only |
| CSRF | `remedy_csrf` | **no** (by design) | env `COOKIE_SECURE` | Lax | double-submit CSRF token |

- No passwords, user ids, roles, health data, or session metadata are stored
  in cookies — only the opaque id and the CSRF token.
- **Development:** `COOKIE_SECURE=false` (plain-HTTP localhost).
- **Production:** `COOKIE_SECURE=true` is **enforced** (startup fails
  otherwise); HSTS is sent automatically.
- `USE_HOST_PREFIXED_COOKIE=true` adds the `__Host-` prefix (requires Secure
  + no Domain) for deployments on a single HTTPS domain.

## CSRF

- Double-submit + HMAC: the CSRF cookie value must be echoed in the
  `X-CSRF-Token` header on **POST/PUT/PATCH/DELETE**; the server also
  verifies the token's HMAC signature (secret: `SECRET_KEY`) and expiry
  (12h). GET/HEAD/OPTIONS are exempt.
- Tokens are minted at `GET /api/v1/auth/csrf` (public, pre-auth) and
  refreshed on every login/registration.
- The signing secret falls back to a deterministic dev derivation locally;
  **production refuses to start** without a real `SECRET_KEY`.

## Authorization

- FastAPI dependencies: `get_current_user`, `require_authenticated_user`,
  `require_role(...)`. Role hierarchy: `user ⊂ reviewer ⊂ admin`
  (`backend/app/dependencies_auth.py`).
- The `reviewer`/`admin` roles are groundwork for the future LangGraph
  human-review workflow. No reviewer UI exists yet (deliberately).
- Every check happens **server-side**; the frontend `RequireAuth` guard is
  convenience, not protection.

## Assessment ownership

- `assessments.user_id` (UUID, FK → users, CASCADE, indexed) stamps every new
  assessment with its owner (migration `c3f8a1d20b47`).
- All reads go through `get_assessment_for_user()` — a foreign or missing id
  yields the **same 404 body** (no existence oracle for guessing UUIDs).
- History listing is filtered by `user_id`; pagination totals are per-user.
- Cross-user LangGraph resume is impossible: checkpoint thread ids are
  user-scoped — `guidance:{user_id}:{assessment_id}`.

## Roles

- `user` — manage own assessments.
- `reviewer` — future human-review workflow actor ( groundwork, unused).
- `admin` — full future administration (groundwork, unused).

## Rate limiting

- Redis fixed-window counters (`ratelimit:{bucket}:{ip-hash}:{window}`) —
  deliberately simple, no distributed machinery.
- `register`: 10/hour, `login`: 20/hour (configurable via
  `AUTH_RATE_LIMIT_*_PER_HOUR`). Exceeding → 429 + `Retry-After`.
- Identifiers are SHA-256 truncated hashes of the client IP — IPs are not
  logged in clear. 429 responses never reveal which limit was hit.

## Security headers

Applied to every response (`backend/app/main.py`):

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` (max-age 1y, includeSubDomains) — **production
  HTTPS only**; never sent in development.
- `Cache-Control: no-store` on all `/api/v1/*` responses (session cookies +
  personalized assessment data must never be cached).

## CORS

- `allow_credentials=True` with **explicit configured origins** only
  (`CORS_ORIGINS`); wildcard + credentials is refused in production.
- Methods: GET/POST/PUT/PATCH/DELETE. Headers: `Content-Type`,
  `X-Request-ID`, `X-CSRF-Token`.

## Secret handling

- No secrets in source. `.env` is gitignored; `.env.example` documents every
  variable with placeholders only.
- `SECRET_KEY` is required in production (startup guard).
- **Git history incident (Phase 5 report), investigated this phase:**
  a local-development PostgreSQL password was hardcoded in
  `backend/app/core/config.py` (introduced in commit `28f14e1`, removed in
  `e24421f`, which replaced it with a placeholder). It was a 4-character
  local-only dev credential — not a production secret. The current tree
  contains no credential; conftest reads test credentials from the
  environment. **Action items:** rotate the local Postgres password anyway
  (cheap insurance), and run history-cleanup (e.g. `git filter-repo` or
  BFG) BEFORE pushing to any truly public repository. The value is NOT
  reproduced anywhere in this documentation.

## Sensitive logging

Never logged: passwords/hashes, session ids, cookies, CSRF tokens, API keys,
medical input values, LLM prompts with patient data. Auth logs are
explicitly PII-free; session Redis errors log only exception type names.
Request IDs, method, path, status, latency remain for operations.

## Development vs production summary

| Concern | Development | Production |
|---|---|---|
| `COOKIE_SECURE` | false (localhost) | **true (enforced)** |
| `SECRET_KEY` | dev fallback derived from DB URL | **required at startup** |
| HSTS | not sent | sent |
| CORS | explicit localhost origins | explicit configured origins only |
| Sessions | Redis (or fail-closed without it) | Redis required |

## Testing

- `backend/tests/test_auth_api.py` — 30 focused tests: registration, Argon2
  storage, generic login failures, server-side logout invalidation, `/me`,
  CSRF (missing/wrong token, safe-method exemption), rate limiting (429),
  ownership scoping, cross-user 404 indistinguishability, session expiry,
  no-store, security headers. Redis is faked in-memory (fakeredis);
  PostgreSQL is the real disposable test DB.
- `frontend/tests/auth.test.tsx` — cookie-session client behavior,
  credentials include, CSRF header propagation, RequireAuth redirect.
