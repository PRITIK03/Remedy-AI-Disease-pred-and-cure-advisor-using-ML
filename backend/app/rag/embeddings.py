"""Embedding client — OpenAI-compatible /embeddings via configuration.

Provider-agnostic: any service exposing POST {base}/embeddings with
{"input": [...], "model": "..."} → {"data": [{"embedding": [...]}]} works
(OpenRouter, OpenAI, Ollama, vLLM, ...). No keys in source; dimension is
configuration and stored per document at ingestion.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("backend.rag.embeddings")


class EmbeddingError(RuntimeError):
    """Raised when the embedding provider fails or returns malformed data."""


class EmbeddingProvider(Protocol):
    """Minimal interface so retrieval/ingestion can be tested with fakes."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns one vector per input."""
        ...


class OpenAICompatibleEmbeddings:
    """Embeddings from any OpenAI-compatible API, configured via settings."""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_base = (api_base or settings.embedding_api_base).rstrip("/")
        self.api_key = api_key or settings.embedding_api_key
        self.model = model or settings.embedding_model
        self.timeout = timeout or settings.embedding_timeout_seconds
        self.dimension = settings.embedding_dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key or not self.model:
            raise EmbeddingError(
                "Embedding provider not configured "
                "(set EMBEDDING_API_KEY and EMBEDDING_MODEL)."
            )
        if not texts:
            return []

        # Batch to keep single requests small; most providers cap batch size.
        batches = [texts[i : i + 32] for i in range(0, len(texts), 32)]
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for batch in batches:
                vectors.extend(self._embed_batch(client, batch))
        self._validate(vectors, texts)
        return vectors

    def _embed_batch(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        try:
            resp = client.post(
                f"{self.api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": batch, "model": self.model},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"Embedding provider returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Embedding provider request failed: {exc}") from exc

        try:
            payload: dict[str, Any] = resp.json()
            data = sorted(payload["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in data]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(
                "Embedding provider returned malformed JSON."
            ) from exc

    def _validate(
        self, vectors: list[list[float]], texts: list[str]
    ) -> None:
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"Embedding provider returned {len(vectors)} vectors "
                f"for {len(texts)} inputs."
            )
        for v in vectors:
            if len(v) != self.dimension:
                raise EmbeddingError(
                    f"Embedding dimension mismatch: provider returned "
                    f"{len(v)}, EMBEDDING_DIMENSION is {self.dimension}. "
                    f"Fix the config or re-ingest with the right model."
                )


def get_embedding_provider() -> EmbeddingProvider:
    """Application-wide provider factory (swap point for tests/alternatives)."""
    return OpenAICompatibleEmbeddings()
