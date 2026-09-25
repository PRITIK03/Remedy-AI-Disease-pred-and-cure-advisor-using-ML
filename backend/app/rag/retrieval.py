"""Evidence retrieval — exact cosine similarity search over pgvector.

Returns structured Evidence objects (never raw DB rows). Designed so a
reranker can be added later without changing the public API: callers get
ranked Evidence lists; internally the ranking strategy is isolated in
`retrieve_relevant_evidence`.
"""

from __future__ import annotations

from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from backend.app.rag.models import KnowledgeChunk
from backend.app.rag.schemas import Evidence

logger = get_logger("backend.rag.retrieval")


class RetrievalUnavailableError(RuntimeError):
    """Raised when the knowledge base cannot serve queries."""


class KnowledgeBaseEmpty(RuntimeError):
    """Raised when no documents are ingested at all."""


def retrieve_relevant_evidence(
    db: Session,
    query: str,
    top_k: int | None = None,
    min_similarity: float | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[Evidence]:
    """Embed the query and return the most similar chunks, best first.

    Exact (sequential-scan) cosine distance search — deliberately simple at
    this scale. A reranker can later slot in between candidate selection and
    the return value without touching callers.
    """
    settings = get_settings()
    top_k = top_k or settings.rag_retrieval_top_k
    min_similarity = (
        settings.rag_min_similarity if min_similarity is None else min_similarity
    )
    provider = embedding_provider or get_embedding_provider()

    # Dimension guard: only chunks embedded with the configured model work.
    vector = provider.embed([query])[0]

    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    stmt = (
        select(
            KnowledgeChunk,
            distance.label("similarity"),
        )
        .order_by(distance.asc())
        .limit(top_k * 3)  # overfetch for threshold + future reranking
    )

    try:
        rows = db.execute(stmt).all()
    except Exception as exc:  # noqa: BLE001 - mapped to a domain error
        raise RetrievalUnavailableError(
            f"Evidence retrieval failed: {exc}"
        ) from exc

    evidence: list[Evidence] = []
    for chunk, sim in rows:
        # pgvector cosine_distance = 1 - cosine_similarity.
        similarity = 1.0 - float(sim)
        if similarity < min_similarity:
            continue
        doc = chunk.document
        evidence.append(
            Evidence(
                title=doc.title,
                source=doc.source_name,
                url=doc.source_url,
                section=chunk.section or "Document",
                content=chunk.content,
                similarity=round(similarity, 4),
            )
        )
        if len(evidence) >= top_k:
            break

    logger.info(
        "Retrieved %d evidence chunks for query (top_k=%s, min_sim=%s)",
        len(evidence),
        top_k,
        min_similarity,
    )
    return evidence


def count_knowledge_documents(db: Session) -> int:
    from sqlalchemy import func

    from backend.app.rag.models import KnowledgeDocument

    return int(db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0)
