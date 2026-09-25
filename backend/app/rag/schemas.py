"""RAG schemas — structured evidence and guidance payloads.

Pydantic is the contract: the backend never returns raw DB rows, and the
LLM's output is validated against these models before it reaches the client
(malformed model output is rejected, not parsed with string matching).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Evidence(BaseModel):
    """One retrieved knowledge chunk — exactly what a citation may reference."""

    title: str = Field(description="Document title from the source manifest.")
    source: str = Field(description="Publisher / institution name.")
    url: HttpUrl = Field(description="Canonical source URL (stored metadata only).")
    section: str = Field(description="Heading/section path the chunk belongs to.")
    content: str = Field(description="The chunk text (verbatim stored content).")
    similarity: float = Field(ge=-1.0, le=1.0, description="Cosine similarity.")


class Citation(BaseModel):
    """A verified citation — must match a retrieved evidence object."""

    title: str
    source: str
    url: HttpUrl
    section: str


class HealthGuidanceResponse(BaseModel):
    """Validated LLM output. The LLM NEVER sees or produces the ML numbers."""

    summary: str = Field(min_length=1, max_length=1200)
    model_explanation: str = Field(min_length=1, max_length=2000)
    key_factors: list[str] = Field(default_factory=list, max_length=10)
    guidance: list[str] = Field(default_factory=list, max_length=10)
    when_to_seek_care: list[str] = Field(default_factory=list, max_length=10)
    limitations: str = Field(min_length=1, max_length=1200)
    citations: list[Citation] = Field(default_factory=list, max_length=8)

    @field_validator("key_factors", "guidance", "when_to_seek_care")
    @classmethod
    def _non_empty_items(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        if v and not cleaned:
            raise ValueError("List fields must not consist of empty strings")
        return cleaned


def verify_citations(
    guidance: HealthGuidanceResponse, evidence: list[Evidence]
) -> list[Citation]:
    """Keep only citations that match a retrieved evidence object.

    A citation is verified when (url, section) — or the url alone — appears
    in the retrieved evidence set. Fabricated citations are dropped; the
    endpoint then builds its citation list from verified evidence only, so
    the UI never shows invented sources.
    """
    evidence_keys = {(str(e.url), e.section) for e in evidence}
    evidence_urls = {str(e.url) for e in evidence}
    verified: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    for c in guidance.citations:
        key = (str(c.url), c.section)
        if key in evidence_keys or (str(c.url) in evidence_urls and key not in seen):
            if key not in seen:
                verified.append(c)
                seen.add(key)
    return verified
