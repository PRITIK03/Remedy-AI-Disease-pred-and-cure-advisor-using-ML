"""Structure-aware chunking for the knowledge base.

Not a blind N-character splitter: paragraphs are grouped under their
section heading into chunks that respect natural boundaries, sized against
token-ish budgets (words), with overlap so boundary content is retrievable
from both neighbors. Heading paths are preserved so citations can point
back to the exact section of a source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.rag.fetcher import normalize_text

MAX_CHUNK_WORDS = 220
MIN_CHUNK_WORDS = 40
OVERLAP_WORDS = 30

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    section: str
    content: str
    chunk_index: int


def _split_oversized(text: str, max_words: int, overlap: int) -> list[str]:
    """Split text longer than max_words on sentence boundaries (never
    mid-word), carrying a small word overlap between consecutive pieces.
    A single 'sentence' longer than the budget (no punctuation) is hard-
    split on words as a last resort."""
    # Budget for sentence assembly excludes the overlap carried between
    # consecutive parts, so each part stays ≤ max_words.
    budget = max(1, max_words - overlap)

    # First: break unreasonably long unpunctuated runs at the word level so
    # sentence assembly below always works on splittable units.
    sentences: list[str] = []
    for s in _SENTENCE_RE.split(text):
        s = s.strip()
        if not s:
            continue
        words = s.split()
        while len(words) > budget:
            sentences.append(" ".join(words[:budget]))
            words = words[budget:]
        if words:
            sentences.append(" ".join(words))

    parts: list[str] = []
    buf: list[str] = []
    words = 0
    for sentence in sentences:
        sw = len(sentence.split())
        if words + sw > budget and buf:
            parts.append(" ".join(buf))
            tail = " ".join(buf).split()[-overlap:]
            buf = [" ".join(tail)] if tail else []
            words = len(tail)
        buf.append(sentence)
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
    """Group section paragraphs into overlapping, heading-carrying chunks.

    Paragraphs of one section accumulate into a chunk until the word budget
    is reached; chunks never span sections. A trailing piece smaller than
    min_words is merged into the section's previous chunk when it fits.
    """
    raw: list[tuple[str, str]] = []  # (section, content) before numbering

    for section, text in sections:
        buf: list[str] = []
        buf_words = 0

        def emit(closed_section: str = section) -> None:
            # Bind the current section as a default arg (B023): the closure
            # must snapshot this iteration's section, not the loop variable.
            nonlocal buf, buf_words
            content = normalize_text(" ".join(buf))
            if content:
                raw.append((closed_section, content))
            buf, buf_words = [], 0

        # Budget for the main body excludes the overlap that will be
        # prepended to the NEXT chunk, so every chunk stays ≤ max_words.
        body_budget = max(1, max_words - overlap)

        for para in (text,):
            pw = len(para.split())
            if pw > max_words:
                if buf:
                    emit()
                pieces = _split_oversized(para, max_words, overlap)
                for piece in pieces:
                    raw.append((section, piece))
                continue
            if buf_words + pw > body_budget and buf:
                emit()
                # Overlap: reopen the new chunk with the tail of the last one.
                tail = raw[-1][1].split()[-overlap:] if raw else []
                if tail:
                    buf.append(" ".join(tail))
                    buf_words = len(tail)
            buf.append(para)
            buf_words += pw

        if buf:
            emit()

        # Merge a trailing undersized chunk of this section into its
        # predecessor when the combined size still fits the budget.
        if (
            raw
            and raw[-1][0] == section
            and len(raw[-1][1].split()) < min_words
        ):
            if len(raw) >= 2 and raw[-2][0] == section and (
                len(raw[-2][1].split()) + len(raw[-1][1].split()) <= max_words
            ):
                merged = normalize_text(raw[-2][1] + " " + raw[-1][1])
                raw[-2:] = [(section, merged)]
            # A lone tiny section stays as-is: dropping content silently
            # would hide evidence; tiny sections are rare and harmless.

    return [
        Chunk(section=sec, content=content, chunk_index=i)
        for i, (sec, content) in enumerate(raw)
    ]
