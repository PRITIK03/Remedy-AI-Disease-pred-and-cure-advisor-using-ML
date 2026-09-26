"""Backend test fixtures.

Database strategy: use REAL PostgreSQL but against a dedicated disposable
database (remedy_ai_test) created/dropped per test session — a developer's
actual remedy_ai database is never touched. Tests that need Redis skip
cleanly when no Redis server is reachable.
"""

from __future__ import annotations

import os
import socket
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Load the repo-root .env (gitignored) BEFORE anything reads os.environ, so
# test DB credentials come from configuration, never from hardcoded source.
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    with _env_file.open(encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Test settings BEFORE importing the app (get_settings is lru_cached).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# Test DB credentials come from the environment / gitignored .env — never
# hardcoded in source. TEST_DB_USER/TEST_DB_PASSWORD are set in .env.example
# for local development; CI provides its own values.
TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.environ.get("TEST_DB_PORT", "5432")
TEST_DB_USER = os.environ.get("TEST_DB_USER", "postgres")
TEST_DB_PASSWORD = os.environ.get("TEST_DB_PASSWORD", "")
TEST_DB = "remedy_ai_test"
ADMIN_URL = (
    f"postgresql+psycopg://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
)
TEST_DATABASE_URL = (
    f"postgresql+psycopg://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB}"
)


def _pg_reachable() -> bool:
    try:
        import psycopg

        with psycopg.connect(
            host=TEST_DB_HOST, port=int(TEST_DB_PORT), user=TEST_DB_USER,
            password=TEST_DB_PASSWORD or None,
            dbname="postgres", connect_timeout=3,
        ):
            return True
    except Exception:  # noqa: BLE001
        return False


def _redis_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 6379), timeout=1):
            return True
    except OSError:
        return False


PG_AVAILABLE = _pg_reachable()
REDIS_AVAILABLE = _redis_reachable()

requires_pg = pytest.mark.skipif(
    not PG_AVAILABLE, reason="PostgreSQL not reachable on localhost:5432"
)
requires_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE, reason="Redis not reachable on localhost:6379"
)


def _make_fake_redis_service():
    """RedisService backed by fakeredis (in-memory) for auth/session tests.

    Tests must exercise the REAL session semantics (TTLs, deletes, double
    submits) without requiring a live Redis server. Returns None only when
    fakeredis is unavailable, in which case auth tests would fail closed.
    """
    try:
        import fakeredis
    except ImportError:
        return None
    from backend.app.services.redis_service import RedisService

    service = RedisService("fakeredis://test")
    service._redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    return service


# --------------------------------------------------------------------------- #
# Auth helpers (Phase 6)
# --------------------------------------------------------------------------- #

CSRF_COOKIE = "remedy_csrf"
SESSION_COOKIE = "remedy_session"


def csrf_headers(client) -> dict:
    """Headers carrying the current CSRF cookie value for unsafe requests."""
    token = client.cookies.get(CSRF_COOKIE)
    return {"X-CSRF-Token": token} if token else {}


def bootstrap_csrf(client) -> str:
    """Mint a CSRF cookie pre-auth (the same flow the frontend uses)."""
    resp = client.get("/api/v1/auth/csrf")
    assert resp.status_code == 200
    return client.cookies.get(CSRF_COOKIE)


def register_and_login(client, email: str, password: str, display_name="Test User"):
    """Register then login; returns the login response."""
    token = bootstrap_csrf(client)
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code in (201, 409), resp.text
    token = bootstrap_csrf(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200, resp.text
    return resp


@pytest.fixture(scope="session")
def test_database_url() -> str:
    if not PG_AVAILABLE:
        pytest.skip("PostgreSQL not reachable")
    import psycopg
    from sqlalchemy import text

    from backend.app.db.session import create_db_engine

    # Create the disposable test database.
    with psycopg.connect(
        host=TEST_DB_HOST, port=int(TEST_DB_PORT), user=TEST_DB_USER,
        password=TEST_DB_PASSWORD or None,
        dbname="postgres", autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE {TEST_DB}')

    # Provision schema via Alembic programmatically (tests the real path).
    from alembic.config import Config

    from alembic import command

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    try:
        command.upgrade(alembic_cfg, "head")
        pgvector_ok = True
    except Exception as exc:
        # pgvector is optional for most tests: if the migration chain fails
        # on the vector extension (not installed server-side), fall back to
        # the Phase 7 revision so core + report tables exist without RAG.
        if "vector" not in str(exc):
            raise
        command.upgrade(alembic_cfg, "b7d19c34e8f2")
        pgvector_ok = False
        print(
            "WARNING: pgvector extension unavailable; RAG tables were NOT "
            "created in the test DB. RAG DB tests will be skipped."
        )

    # Sanity: tables exist.
    engine = create_db_engine(TEST_DATABASE_URL)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
        }
    engine.dispose()
    assert {"assessments", "users"} <= tables

    os.environ["PGVECTOR_AVAILABLE"] = "1" if pgvector_ok else "0"
    return TEST_DATABASE_URL


@pytest.fixture()
def app(test_database_url):
    """FastAPI app with lifespan run against the disposable test DB."""
    from backend.app.core.config import get_settings
    from backend.app.main import app as fastapi_app

    get_settings.cache_clear()
    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()

    fastapi_app.state.session_factory = None
    with TestClientContext(fastapi_app) as _:
        yield fastapi_app


class TestClientContext:
    """Run FastAPI lifespan manually (sync-safe helper for tests)."""

    def __init__(self, app):
        self.app = app

    def __enter__(self):
        import asyncio

        from backend.app.db.session import create_db_engine, create_session_factory

        async def _startup():
            # Recreate services the same way lifespan does, bound to test DB.
            from backend.app.services.model_service import ModelService

            self.app.state.model_service = ModelService()
            self.app.state.model_service.load(None)
            self.app.state.redis_service = _make_fake_redis_service()
            self.app.state.db_engine = create_db_engine(TEST_DATABASE_URL)
            self.app.state.session_factory = create_session_factory(
                self.app.state.db_engine
            )

        asyncio.run(_startup())
        return self.app

    def __exit__(self, *exc):
        import asyncio

        async def _shutdown():
            rs = getattr(self.app.state, "redis_service", None)
            if rs is not None:
                await rs.close()
            engine = getattr(self.app.state, "db_engine", None)
            if engine is not None:
                engine.dispose()

        asyncio.run(_shutdown())
        return False


class CSRFClient(TestClient):
    """TestClient that auto-echoes the CSRF cookie into the required header
    for unsafe requests (mirrors what the real frontend does). An explicitly
    provided X-CSRF-Token is never overridden, so negative tests still work."""

    def request(self, method, url, **kwargs):  # noqa: D102
        headers = dict(kwargs.get("headers") or {})
        if "X-CSRF-Token" not in headers:
            token = self.cookies.get(CSRF_COOKIE)
            if token:
                headers["X-CSRF-Token"] = token
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        # The lifespan overwrites services with real-config instances; swap
        # back the in-memory fake Redis so session/rate-limit behavior is
        # deterministic and no live Redis is required.
        fake = _make_fake_redis_service()
        if fake is not None:
            test_client.app.state.redis_service = fake
        yield test_client


@pytest.fixture()
def auth_client(app):
    """CSRF-auto-echoing client logged in as a unique fresh user.

    Used by pre-auth suites (test_api.py, test_guidance_api.py) so their
    business assertions stay unchanged; ownership/CSRF behavior is covered
    by the Phase 6 suite with the raw `client` fixture.
    """
    with CSRFClient(app) as test_client:
        # Swap in the fake Redis AFTER the lifespan has run (the lifespan
        # overwrites app.state with real-config services).
        fake = _make_fake_redis_service()
        if fake is not None:
            test_client.app.state.redis_service = fake
        email = f"legacy-{uuid.uuid4().hex[:12]}@example.com"
        bootstrap_csrf(test_client)
        resp = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "legacy-suite-password",
                "display_name": "Legacy Suite User",
            },
        )
        assert resp.status_code == 201, resp.text
        yield test_client


@pytest.fixture(autouse=True)
def clean_assessments_table(test_database_url):
    """Isolate each test: truncate users + assessments + reports between tests."""
    if not PG_AVAILABLE:
        yield
        return
    from backend.app.db.session import create_db_engine

    engine = create_db_engine(TEST_DATABASE_URL)
    yield
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE report_extractions, assessments, medical_reports, users CASCADE"
            )
        )
    engine.dispose()
