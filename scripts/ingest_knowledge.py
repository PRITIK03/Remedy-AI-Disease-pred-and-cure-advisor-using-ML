"""Knowledge base ingestion — sources.yaml → fetch → chunk → embed → store.

Deterministic and idempotent:
  - document identity = normalized source URL (unique index)
  - document content hash = sha256 of the full normalized text; an unchanged
    document is skipped entirely
  - chunk identity = (document_id, chunk content hash) — unique index; a
    changed document is replaced atomically (delete chunks + re-insert)

Usage:
    .venv/Scripts/python -m scripts.ingest_knowledge            # full run
    .venv/Scripts/python -m scripts.ingest_knowledge --dry-run  # no writes
    .venv/Scripts/python -m scripts.ingest_knowledge --url <u>  # one source

Never run automatically per API request.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.db.session import create_db_engine, create_session_factory
from backend.app.rag.chunking import chunk_sections
from backend.app.rag.embeddings import EmbeddingError, get_embedding_provider
from backend.app.rag.fetcher import fetch_document
from backend.app.rag.models import KnowledgeChunk, KnowledgeDocument
from backend.app.rag.sources import ManifestError, load_manifest

logger = get_logger("scripts.ingest_knowledge")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_document(
    db: Session,
    record,
    dry_run: bool = False,
) -> str:
    """Ingest one manifest record. Returns: 'created' | 'unchanged' | 'updated'.

    Raises on fetch/embedding failure — the caller decides whether to abort.
    """
    settings = get_settings()
    provider = get_embedding_provider()

    # 1. Fetch + normalize.
    with httpx.Client(timeout=30.0) as client:
        doc = fetch_document(client, record.url)
    if not doc.ok:
        raise RuntimeError(f"Fetch failed for {record.url} (status={doc.status_code})")

    # 2. Chunk (structure-aware).
    chunks = chunk_sections(doc.sections)
    if not chunks:
        raise RuntimeError(f"No content extracted from {record.url}")
    full_text_hash = sha256("\n".join(c.content for c in chunks))

    # 3. Duplicate check at document level.
    existing = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.source_url == record.url
        )
    )
    if existing is not None:
        if existing.content_hash == full_text_hash and (
            existing.embedding_model == settings.embedding_model
        ):
            return "unchanged"
        # Content or embedding model changed → replace atomically.
        if not dry_run:
            db.delete(existing)
            db.flush()
        existing = None
        status = "updated"
    else:
        status = "created"

    if dry_run:
        return status

    # 4. Embeddings (batched, once, before any DB writes).
    try:
        vectors = provider.embed([c.content for c in chunks])
    except EmbeddingError:
        raise
    if len(vectors) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch for {record.url}: "
            f"{len(vectors)} vectors for {len(chunks)} chunks"
        )

    document = KnowledgeDocument(
        title=record.title,
        source_url=record.url,
        source_name=record.publisher,
        document_type=record.document_type,
        publication_date=None,  # extracted when a source exposes it reliably
        retrieved_at=datetime.now(UTC),
        content_hash=full_text_hash,
        license_note=record.license_note or None,
        embedding_model=settings.embedding_model,
        embedding_dimension=settings.embedding_dimension,
    )
    db.add(document)
    db.flush()  # assign document.id

    for chunk, vector in zip(chunks, vectors, strict=True):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                section=chunk.section,
                content=chunk.content,
                content_hash=sha256(chunk.content),
                embedding=vector,
            )
        )
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest knowledge sources.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and chunk but write nothing."
    )
    parser.add_argument("--url", action="append", default=[], help="Only these URLs.")
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="Abort on the first failed source (default: skip and report).",
    )
    args = parser.parse_args(argv)

    configure_logging("INFO")
    settings = get_settings()
    if not settings.rag_configured:
        logger.error(
            "Embedding provider not configured: set EMBEDDING_API_KEY and "
            "EMBEDDING_MODEL in .env (see .env.example)."
        )
        return 2

    try:
        records = load_manifest()
    except ManifestError as exc:
        logger.error("Manifest error: %s", exc)
        return 2
    if args.url:
        wanted = set(args.url)
        records = [r for r in records if r.url in wanted]

    engine = create_db_engine()
    SessionLocal = create_session_factory(engine)
    results: dict[str, str] = {}
    failed: list[tuple[str, str]] = []

    with SessionLocal() as db:
        for record in records:
            try:
                outcome = ingest_document(db, record, dry_run=args.dry_run)
                results[record.url] = outcome
                logger.info("[%s] %s", outcome.upper(), record.url)
            except Exception as exc:  # noqa: BLE001 - per-source isolation
                failed.append((record.url, str(exc)))
                logger.error("[FAILED] %s: %s", record.url, exc)
                db.rollback()
                if args.fail_fast:
                    break
        if not args.dry_run and not failed:
            db.commit()
        elif not args.dry_run:
            db.commit()  # commit per-source successes; failures were rolled back

    created = sum(1 for v in results.values() if v == "created")
    updated = sum(1 for v in results.values() if v == "updated")
    unchanged = sum(1 for v in results.values() if v == "unchanged")
    print(
        f"\nIngestion summary: {created} created, {updated} updated, "
        f"{unchanged} unchanged, {len(failed)} failed."
    )
    if failed:
        for url, err in failed:
            print(f"  FAILED {url}: {err[:160]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
