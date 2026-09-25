"""Document fetching + text normalization for knowledge ingestion.

Fetches manifest URLs over HTTPS, strips scripts/styles/navigation, and
extracts clean section-structured text. No content is committed to the
repository — the DB is the store, with provenance metadata per document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

from backend.app.core.logging import get_logger

logger = get_logger("backend.rag.fetcher")

USER_AGENT = "RemedyAI-KnowledgeIngest/1.0 (educational prototype)"
FETCH_TIMEOUT = 30.0

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|svg|head)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAV_CLASS_HINTS = re.compile(
    r"(nav|menu|footer|header|breadcrumb|sidebar|promo|share|social|newsletter|"
    r"related|feedback|cookie|advertisement|skip-link)",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    """Extracts (heading_path, text) blocks from HTML."""

    BLOCK_TAGS = {
        "p", "li", "tr", "div", "section", "article", "blockquote",
        "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "dd", "dt",
    }
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[tuple[str, str]] = []  # (heading_path, text)
        self._heading_stack: list[str] = []
        self._buf: list[str] = []
        self._skip_depth = 0
        self._skip_tag = ""
        self._in_blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        attrs_d = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "template", "form", "button"):
            self._skip_depth = 1
            self._skip_tag = tag
            return
        if self._skip_depth:
            self._skip_depth += 1
            return
        cls = attrs_d.get("class", "") + " " + attrs_d.get("id", "")
        if tag in ("nav", "footer", "aside") or NAV_CLASS_HINTS.search(cls):
            self._in_blocked += 1
            return
        if tag in self.HEADING_TAGS:
            self._flush()
            level = int(tag[1])
            # Keep the heading hierarchy coherent when jumping levels.
            while self._heading_stack and len(self._heading_stack) >= level:
                self._heading_stack.pop()
            self._heading_stack.append(attrs_d.get("id") or f"heading{len(self.paragraphs)}")
            return
        if tag in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth = 0
            else:
                self._skip_depth -= 1
                return
        if tag in ("nav", "footer", "aside") and self._in_blocked:
            self._in_blocked -= 1
            return
        if tag in self.BLOCK_TAGS or tag in self.HEADING_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and not self._in_blocked:
            self._buf.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if len(text) >= 3:
            path = " > ".join(self._heading_stack) if self._heading_stack else "Introduction"
            self.paragraphs.append((path, text))

    def close(self) -> None:  # noqa: D102 - override
        self._flush()
        super().close()


@dataclass
class FetchedDocument:
    url: str
    status_code: int
    sections: list[tuple[str, str]] = field(default_factory=list)  # (heading, text)

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and bool(self.sections)


def normalize_text(text: str) -> str:
    """Collapse whitespace, drop control chars — stable before hashing."""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_document(client: httpx.Client, url: str) -> FetchedDocument:
    """Fetch one URL and extract section-structured paragraphs."""
    try:
        resp = client.get(
            url, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
        return FetchedDocument(url=url, status_code=0)

    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype:
        logger.warning("Skipping non-HTML content at %s (%s)", url, ctype)
        return FetchedDocument(url=url, status_code=resp.status_code)

    html = resp.text
    html = _COMMENT_RE.sub(" ", html)
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception as exc:  # noqa: BLE001 - malformed HTML must not crash ingestion
        logger.warning("HTML parse failed for %s: %s", url, exc)
        return FetchedDocument(url=url, status_code=resp.status_code)

    sections = [
        (normalize_text(h), normalize_text(t)) for h, t in extractor.paragraphs
    ]
    # Drop near-duplicate paragraphs that survive template noise.
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for h, t in sections:
        if t not in seen:
            seen.add(t)
            deduped.append((h, t))
    return FetchedDocument(url=url, status_code=resp.status_code, sections=deduped)
