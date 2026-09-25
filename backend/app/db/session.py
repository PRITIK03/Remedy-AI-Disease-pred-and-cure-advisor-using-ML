"""Engine/session management for PostgreSQL (psycopg 3) via SQLAlchemy 2.0."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


def create_db_engine(database_url: str | None = None, **engine_kwargs: Any):
    settings = get_settings()
    url = database_url or settings.database_url
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
    }
    # SQLite (used by some tests) doesn't accept pooling kwargs.
    if url.startswith("sqlite"):
        kwargs = {}
    kwargs.update(engine_kwargs)
    return create_engine(url, **kwargs)


def create_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def build_session_dependency(factory: sessionmaker[Session]):
    """Return a FastAPI dependency yielding a database session."""

    def get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return get_db
