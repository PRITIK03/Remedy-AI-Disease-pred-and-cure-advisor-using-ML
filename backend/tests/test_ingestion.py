"""Phase 4 ingestion test — idempotency + duplicate prevention.

Uses a TINY local fixture document (no network) and a fake embedding
provider. Skips when pgvector is unavailable server-side (conftest sets
PGVECTOR_AVAILABLE=0 after the migration fallback).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.tests.conftest import PG_AVAILABLE  # noqa: E402

requires_pgvector = pytest.mark.skipif(
    not PG_AVAILABLE or os.environ.get("PGVECTOR_AVAILABLE") != "1",
    reason="pgvector extension unavailable server-side",
)


@dataclass
class _FakeRecord:
    url: str
    title: str
    publisher: str
    document_type: str = "fixture"
    license_note: str = "test fixture"
    section_selectors: list = None  # type: ignore[assignment]


class _FakeEmbeddings:
    """Deterministic fake embedding provider (hash-based vectors)."""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def embed(self, texts):
        import hashlib

        vectors = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [(h[i % len(h)] / 255.0) for i in range(self.dim)]
            vectors.append(vec)
        return vectors


@pytest.fixture()
def fresh_tables(test_database_url):
    """Truncate knowledge tables between ingestion tests."""
    from sqlalchemy import text

    from backend.app.db.session import create_db_engine

    engine = create_db_engine(test_database_url)
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE knowledge_chunks, knowledge_documents CASCADE"))
    engine.dispose()


@requires_pgvector
class TestIngestionIdempotency:
    def test_double_ingest_no_duplicates(self, test_database_url, fresh_tables, monkeypatch):
        """Phase requirement: running ingestion twice must not duplicate."""
        from sqlalchemy import func, select

        from backend.app.rag.models import KnowledgeChunk, KnowledgeDocument
        from scripts.ingest_knowledge import ingest_document

        record = _FakeRecord(
            url="https://www.nhs.uk/conditions/atherosclerosis/",
            title="Atherosclerosis (fixture)",
            publisher="UK National Health Service",
        )
        sections = [
            ("What is it", "Atherosclerosis is the narrowing of arteries. " * 10),
            ("Prevention", "A healthy diet lowers the risk. " * 10),
        ]
        # Bypass the network fetch: monkeypatch fetch_document inside the
        # ingestion module namespace with a fixture-based fake.
        import backend.app.rag.fetcher as fetcher_mod
        from backend.app.rag.fetcher import FetchedDocument

        monkeypatch.setattr(
            fetcher_mod,
            "fetch_document",
            lambda client, url: FetchedDocument(
                url=url, status_code=200, sections=sections
            ),
        )
        import scripts.ingest_knowledge as ingest_mod

        monkeypatch.setattr(
            ingest_mod, "get_embedding_provider", lambda: _FakeEmbeddings()
        )
        # Force a deterministic fake "config" model name.
        monkeypatch.setattr(
            type(ingest_mod.get_settings()),
            "embedding_model",
            property(lambda self: "fake-embed-model"),
        )

        from backend.app.db.session import create_db_engine, create_session_factory

        engine = create_db_engine(test_database_url)
        SessionLocal = create_session_factory(engine)

        with SessionLocal() as db:
            first = ingest_document(db, record)
            db.commit()
            assert first == "created"

            # Second ingestion of identical content → unchanged, no copies.
            second = ingest_document(db, record)
            db.commit()
            assert second == "unchanged"

        docs = SessionLocal().scalar(
            select(func.count()).select_from(KnowledgeDocument)
        )
        chunks = SessionLocal().scalar(
            select(func.count()).select_from(KnowledgeChunk)
        )
        assert docs == 1, "duplicate document created!"
        assert chunks > 0
        engine.dispose()

    def test_changed_content_updates(self, test_database_url, fresh_tables, monkeypatch):
        """Changed source content replaces the document (updated, not dup'd)."""
        from sqlalchemy import func, select

        from backend.app.rag.models import KnowledgeDocument
        from scripts.ingest_knowledge import ingest_document

        record = _FakeRecord(
            url="https://www.nhs.uk/conditions/atherosclerosis/",
            title="Atherosclerosis (fixture)",
            publisher="UK National Health Service",
        )
        sections_v1 = [("What", "Original content text. " * 10)]
        sections_v2 = [("What", "Updated content text. " * 10)]

        import backend.app.rag.fetcher as fetcher_mod
        from backend.app.rag.fetcher import FetchedDocument

        current = {"sections": sections_v1}
        monkeypatch.setattr(
            fetcher_mod,
            "fetch_document",
            lambda client, url: FetchedDocument(
                url=url, status_code=200, sections=current["sections"]
            ),
        )
        import scripts.ingest_knowledge as ingest_mod

        monkeypatch.setattr(
            ingest_mod, "get_embedding_provider", lambda: _FakeEmbeddings()
        )
        monkeypatch.setattr(
            type(ingest_mod.get_settings()),
            "embedding_model",
            property(lambda self: "fake-embed-model"),
        )

        from backend.app.db.session import create_db_engine, create_session_factory

        engine = create_db_engine(test_database_url)
        SessionLocal = create_session_factory(engine)

        with SessionLocal() as db:
            assert ingest_document(db, record) == "created"
            db.commit()
            current["sections"] = sections_v2
            assert ingest_document(db, record) == "updated"
            db.commit()

        docs = SessionLocal().scalar(
            select(func.count()).select_from(KnowledgeDocument)
        )
        assert docs == 1
        engine.dispose()
