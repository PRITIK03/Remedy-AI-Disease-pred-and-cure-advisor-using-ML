"""Structure-aware chunking for the knowledge base.

Not a blind N-character splitter: paragraphs are grouped under their
section heading into chunks that respect natural boundaries, sized against
token-ish budgets (words), with overlap so boundary content is retrievable
from both neighbors. Heading paths are preserved so citations can point
back to the exact section of a source.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.rag.fetcher import normalize_text

MAX_CHUNK_WORDS = 220
MIN_CHUNK_WORDS = 40
OVERLAP_WORDS = 30


@dataclass(frozen=True)
class Chunk:
    section: str
    content: str
    chunk_index: int


def _split_long_paragraph(text: str) -> list[str]:
    """Split an oversized paragraph on sentence boundaries (never mid-word)."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts: list[str] = []
    buf: list[str] = []
    words = 0
    for s in sentences:
        sw = len(s.split())
        if words + sw > MAX_CHUNK_WORDS and buf:
            parts.append(" ".join(buf))
            buf, words = [], 0
            # carry overlap for continuity across the split
            tail = " ".join(" ".join(buf).split()[-OVERLAP_WORDS:])
            if tail:
                buf.append(tail)
                words = len(tail.split())
        buf.append(s)
        words += sw
    if buf:
        parts.append(" ".join(buf))
    return parts


def chunk_sections(
    sections: list[tuple[str, str]],
    max_words: int = MAX_CHUNK_WORDS,
    min_words: int = MIN_CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> list[Chunk]:
    """Group section paragraphs into overlapping, heading-carrying chunks."""
    chunks: list[Chunk] = []
    index = 0

    for section, text in sections:
        paragraphs = [p for p in text.split("  ") if p.strip()] or [text]
        # Flatten: each source paragraph joins the current chunk buffer.
        buffer: list[str] = []
        buffer_words = 0

        def flush() -> None:
            nonlocal buffer, buffer_words, index
            if buffer_words >= max(0, min_words) // 2 or buffer:
                content = normalize_text(" ".join(buffer))
                if content.split():
                    chunks.append(
                        Chunk(section=section, content=content, chunk_index=index)
                    )
                    index += 1
            buffer, buffer_words = [], 0

        for para in paragraphs:
            pw = len(para.split())
            if pw > max_words:
                # Flush what we have, then chunk the giant paragraph itself.
                if buffer:
                    flush()
                for piece in _split_long_paragraph(para):
                    pieces_w = len(piece.split())
                    if buffer_words + pieces_w > max_words and buffer:
                        flush()
                    buffer.append(piece)
                    buffer_words += pieces_w
                continue
            if buffer_words + pw > max_words and buffer:
                flush()
                # Overlap: reopen with the tail of the previous chunk.
                tail = " ".join(
                    " ".join(buffer).split()[-overlap:]
                ) if buffer else ""
                if tail:
                    buffer.append(tail)
                    buffer_words = len(tail.split())
            buffer.append(para)
            buffer_words += pw

        if buffer:
            flush()

    # Merge tiny trailing chunks into predecessors where possible.
    merged: list[Chunk] = []
    for chunk in chunks:
        if (
            merged
            and len(chunk.content.split()) < min_words
            and merged[-1].section == chunk.section
            and len(merged[-1].content.split()) + len(chunk.content.split()) <= max_words
        ):
            merged[-1] = Chunk(
                section=merged[-1].section,
                content=normalize_text(f"{merged[-1].content} {chunk.content}"),
                chunk_index=merged[-1].chunk_index,
            )
        else:
            if merged and chunk.chunk_index != len(merged):
                chunk = Chunk(
                    section=chunk.section,
                    content=chunk.content,
                    chunk_index=len(merged),
                )
            merged.append(chunk)
    return merged
