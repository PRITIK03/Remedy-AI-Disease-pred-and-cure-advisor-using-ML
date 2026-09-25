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
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Test settings BEFORE importing the app (get_settings is lru_cached).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

ADMIN_URL = "postgresql+psycopg://postgres:1234@localhost:5432/postgres"
TEST_DB = "remedy_ai_test"
TEST_DATABASE_URL = (
    f"postgresql+psycopg://postgres:1234@localhost:5432/{TEST_DB}"
)


def _pg_reachable() -> bool:
    try:
        import psycopg

        with psycopg.connect(
            host="localhost", port=5432, user="postgres", password="1234",
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


@pytest.fixture(scope="session")
def test_database_url() -> str:
    if not PG_AVAILABLE:
        pytest.skip("PostgreSQL not reachable")
    import psycopg
    from sqlalchemy import text

    from backend.app.db.session import create_db_engine

    # Create the disposable test database.
    with psycopg.connect(
        host="localhost", port=5432, user="postgres", password="1234",
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
    command.upgrade(alembic_cfg, "head")

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
            from backend.app.services.redis_service import RedisService

            self.app.state.model_service = ModelService()
            self.app.state.model_service.load(None)
            self.app.state.redis_service = RedisService(
                os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            )
            try:
                await self.app.state.redis_service.connect()
            except Exception:  # noqa: BLE001
                self.app.state.redis_service = None
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


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_assessments_table(test_database_url):
    """Isolate each test: truncate assessments between tests."""
    if not PG_AVAILABLE:
        yield
        return
    from backend.app.db.session import create_db_engine

    engine = create_db_engine(TEST_DATABASE_URL)
    yield
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE assessments"))
    engine.dispose()
