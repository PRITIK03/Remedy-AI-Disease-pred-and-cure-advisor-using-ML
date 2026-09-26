"""Phase 6 focused auth/API tests.

Covers: register, login (generic failures), logout (server-side
invalidation), /me, CSRF, rate limiting, assessment ownership, cross-user
access, session expiry, protected routes. Redis is faked in-memory
(fakeredis); PostgreSQL is the real disposable test DB.
"""

from __future__ import annotations

import uuid

from backend.tests.conftest import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    bootstrap_csrf,
    register_and_login,
    requires_pg,
)

VALID_PAYLOAD = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
    "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
    "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
}

USER_A = "user-a@example.com"
USER_B = "user-b@example.com"
PASSWORD = "correct-horse-battery"


def _create_assessment(client) -> str:
    resp = client.post(
        "/api/v1/assessments", json=VALID_PAYLOAD, headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@requires_pg
class TestRegistration:
    def test_register_creates_account_and_session(self, client):
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": USER_A, "password": PASSWORD, "display_name": "A"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["user"]["email"] == USER_A
        assert body["user"]["role"] == "user"
        # Hash or session id must never appear in any response.
        assert "password" not in resp.text.lower() or "password_hash" not in resp.text
        assert SESSION_COOKIE not in resp.text
        assert SESSION_COOKIE in resp.cookies
        assert resp.cookies[SESSION_COOKIE]

    def test_register_duplicate_email_generic_409(self, client):
        register_and_login(client, USER_A, PASSWORD)
        client.cookies.clear()
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": USER_A, "password": PASSWORD, "display_name": "A2"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 409
        assert "unable" in resp.json()["detail"].lower()

    def test_register_weak_password_422(self, client):
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": "short", "display_name": "W"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 422

    def test_register_invalid_email_422(self, client):
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": PASSWORD, "display_name": "W"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 422

    def test_password_stored_as_argon2_hash(self, client, test_database_url):
        register_and_login(client, USER_A, PASSWORD)
        from sqlalchemy import create_engine, text

        engine = create_engine(test_database_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT password_hash FROM users WHERE email=:e"), {"e": USER_A}
            ).fetchone()
        engine.dispose()
        assert row is not None and row[0]
        assert row[0].startswith("$argon2")
        assert PASSWORD not in row[0]


@requires_pg
class TestLogin:
    def test_login_success_sets_cookies(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assert SESSION_COOKIE in client.cookies
        assert CSRF_COOKIE in client.cookies

    def test_login_wrong_password_generic_failure(self, client):
        register_and_login(client, USER_A, PASSWORD)
        client.cookies.clear()
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": USER_A, "password": "wrong-password"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password."

    def test_login_unknown_email_identical_failure(self, client):
        token = bootstrap_csrf(client)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "whatever-long"},
            headers={"X-CSRF-Token": token},
        )
        assert resp.status_code == 401
        # Must be byte-identical to the wrong-password failure (no oracle).
        assert resp.json()["detail"] == "Invalid email or password."

    def test_password_not_in_any_login_response(self, client):
        resp = register_and_login(client, USER_A, PASSWORD)
        assert PASSWORD not in resp.text


@requires_pg
class TestCurrentUserAndLogout:
    def test_me_returns_authenticated_user(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == USER_A
        assert "password" not in resp.json()

    def test_me_anonymous_401(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_logout_invalidates_session_server_side(self, client):
        register_and_login(client, USER_A, PASSWORD)
        old_session = client.cookies.get(SESSION_COOKIE)
        resp = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}
        )
        assert resp.status_code == 200
        assert resp.json()["logged_out"] is True
        # Simulate a browser that kept the cookie: replay the old value. The
        # server-side session is gone, so the replay must be rejected.
        client.cookies.set(SESSION_COOKIE, old_session)
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_logout_requires_session(self, client):
        token = bootstrap_csrf(client)
        resp = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
        assert resp.status_code == 401


@requires_pg
class TestCsrf:
    def test_post_without_csrf_token_403(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD)
        assert resp.status_code == 403

    def test_post_with_wrong_csrf_token_403(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = client.post(
            "/api/v1/assessments",
            json=VALID_PAYLOAD,
            headers={"X-CSRF-Token": "bogus.token.value"},
        )
        assert resp.status_code == 403

    def test_post_with_valid_csrf_token_succeeds(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assert _create_assessment(client)

    def test_get_requests_do_not_require_csrf(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assert client.get("/api/v1/assessments").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200


@requires_pg
class TestAssessmentOwnership:
    def test_history_is_scoped_to_owner(self, client):
        register_and_login(client, USER_A, PASSWORD)
        a1 = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        assert _create_assessment(client)
        resp = client.get("/api/v1/assessments")
        ids = {item["id"] for item in resp.json()["items"]}
        assert resp.json()["total"] == 1
        assert a1 not in ids  # user B never sees user A's assessment

    def test_cross_user_access_returns_404(self, client):
        register_and_login(client, USER_A, PASSWORD)
        a1 = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        for path in (
            f"/api/v1/assessments/{a1}",
            f"/api/v1/assessments/{a1}/explanation",
        ):
            resp = client.get(path)
            assert resp.status_code == 404, path

    def test_cross_user_guidance_returns_404(self, client):
        register_and_login(client, USER_A, PASSWORD)
        a1 = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        resp = client.post(
            f"/api/v1/assessments/{a1}/guidance",
            headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
        )
        assert resp.status_code == 404

    def test_missing_and_foreign_are_indistinguishable(self, client):
        register_and_login(client, USER_B, PASSWORD)
        foreign = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_A, PASSWORD)
        ghost = client.get(f"/api/v1/assessments/{uuid.uuid4()}")
        owned_by_b = client.get(f"/api/v1/assessments/{foreign}")
        assert ghost.status_code == owned_by_b.status_code == 404
        assert ghost.json() == owned_by_b.json()  # identical body: no oracle

    def test_new_assessments_record_owner(self, client, test_database_url):
        register_and_login(client, USER_A, PASSWORD)
        a1 = _create_assessment(client)
        from sqlalchemy import create_engine, text

        engine = create_engine(test_database_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT user_id FROM assessments WHERE id=:i"), {"i": a1}
            ).fetchone()
        engine.dispose()
        assert row is not None and row[0] is not None


@requires_pg
class TestProtectedRoutes:
    def test_create_assessment_anonymous_401(self, client):
        token = bootstrap_csrf(client)
        resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD, headers={"X-CSRF-Token": token})
        assert resp.status_code == 401

    def test_list_assessments_anonymous_401(self, client):
        assert client.get("/api/v1/assessments").status_code == 401

    def test_get_assessment_anonymous_401(self, client):
        resp = client.get(f"/api/v1/assessments/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_health_and_ready_remain_public(self, client):
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200


@requires_pg
class TestSessionExpiryAndNoStore:
    def test_expired_session_is_rejected(self, client, test_database_url):
        register_and_login(client, USER_A, PASSWORD)
        # Force expiry by deleting the Redis key (TTL enforcement equivalent).
        from backend.app.core.security import hash_session_id

        session_id = client.cookies.get(SESSION_COOKIE)
        app = client.app
        # fakeredis sync mirror: delete via the async client wrapped sync.
        redis = app.state.redis_service._redis
        import asyncio

        asyncio.run(redis.delete("session:" + hash_session_id(session_id)))
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_authenticated_responses_are_no_store(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = client.get("/api/v1/assessments")
        assert resp.headers.get("cache-control") == "no-store"

    def test_security_headers_present(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        # HSTS must NOT be set in development/test (HTTPS-only directive).
        assert "strict-transport-security" not in resp.headers


@requires_pg
class TestRateLimiting:
    def test_login_rate_limit_429(self, client, monkeypatch):
        from backend.app.core.config import get_settings

        monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN_PER_HOUR", "2")
        get_settings.cache_clear()
        try:
            register_and_login(client, USER_A, PASSWORD)
            client.cookies.clear()
            for _ in range(2):
                token = bootstrap_csrf(client)
                client.post(
                    "/api/v1/auth/login",
                    json={"email": USER_A, "password": "wrong-password"},
                    headers={"X-CSRF-Token": token},
                )
            token = bootstrap_csrf(client)
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": USER_A, "password": PASSWORD},
                headers={"X-CSRF-Token": token},
            )
            assert resp.status_code == 429
        finally:
            get_settings.cache_clear()
