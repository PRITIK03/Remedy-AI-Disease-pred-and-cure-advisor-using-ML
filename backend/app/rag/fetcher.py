"""Document fetching + text normalization for knowledge ingestion.

Fetches manifest URLs over HTTPS, strips scripts/styles/navigation, and
extracts clean section-structured text (heading path → paragraphs). No
content is committed to the repository — the DB is the store, with
provenance metadata per document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

from backend.app.core.logging import get_logger

logger = get_logger("backend.rag.fetcher")

# Browser-like UA: several health sites (CDC) reject obvious bot agents.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 RemedyAI-Educational/1.0"
)
FETCH_TIMEOUT = 30.0

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_NAV_CLASS_HINTS = re.compile(
    r"(^|[\s_-])(nav|navbar|menu|footer|header|breadcrumb|sidebar|promo|share|"
    r"social|newsletter|related-articles|feedback|cookie|advertisement|"
    r"skip-link|pagination|tags|rating)",
    re.IGNORECASE,
)
_SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "form", "button", "iframe"}
_BLOCKED_TAGS = {"nav", "footer", "aside"}
_BLOCK_TAGS = {
    "p", "li", "tr", "div", "section", "article", "blockquote", "main",
    "figcaption", "dd", "dt", "table", "ul", "ol",
}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    """Extracts (heading_path, paragraph_text) blocks from HTML.

    Heading paths are real heading texts joined with ' > ' so citations can
    point back to the exact section of a source page.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[tuple[str, str]] = []
        self._heading_path: list[str] = []
        self._heading_buf: list[str] | None = None  # collecting heading text
        self._buf: list[str] = []
        self._skip_stack: list[str] = []   # script/style/etc. nesting
        self._blocked_stack: list[str] = []  # nav-like container nesting

    # -- helpers --------------------------------------------------------- #
    def _flush_paragraph(self) -> None:
        if self._heading_buf is not None:
            return  # paragraph buffer unused while collecting a heading
        text = " ".join("".join(self._buf).split()).strip("\ufeff")
        self._buf = []
        if len(text) >= 3:
            path = " > ".join(self._heading_path) if self._heading_path else "Introduction"
            self.paragraphs.append((path, text))

    def _capture_heading(self) -> None:
        text = " ".join("".join(self._heading_buf or []).split())
        self._heading_buf = None
        if not text:
            return
        self._heading_path.append(text[:200])

    # -- parser events ---------------------------------------------------- #
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        attrs_d = dict(attrs)
        if self._skip_stack:
            if tag in self._skip_stack or tag in _SKIP_TAGS:
                self._skip_stack.append(tag)
            return
        if self._heading_buf is not None:
            # Inline markup inside a heading — keep collecting its text.
            return
        if tag in _SKIP_TAGS:
            self._skip_stack.append(tag)
            return
        cls_id = attrs_d.get("class", "") + " " + attrs_d.get("id", "")
        if tag in _BLOCKED_TAGS or _NAV_CLASS_HINTS.search(cls_id):
            self._blocked_stack.append(tag)
            self._flush_paragraph()
            return
        if tag in _HEADING_TAGS:
            self._flush_paragraph()
            # New heading context: trim the path to the parent level.
            level = int(tag[1])
            while len(self._heading_path) >= level:
                self._heading_path.pop()
            self._heading_buf = []
            return
        if tag in _BLOCK_TAGS:
            self._flush_paragraph()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack:
            if tag in self._skip_stack:
                # Pop until the matching opener (handles nested same-tags).
                while self._skip_stack:
                    if self._skip_stack.pop() == tag:
                        break
            return
        if tag in _HEADING_TAGS and self._heading_buf is not None:
            self._capture_heading()
            return
        if self._blocked_stack and tag in self._blocked_stack:
            while self._blocked_stack:
                if self._blocked_stack.pop() == tag:
                    break
            return
        if tag in _BLOCK_TAGS or tag in _HEADING_TAGS:
            self._flush_paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip_stack or self._blocked_stack:
            return
        if self._heading_buf is not None:
            self._heading_buf.append(data)
        else:
            self._buf.append(data)

    def close(self) -> None:  # noqa: D102
        self._flush_paragraph()
        self._capture_heading()
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
    text = text.replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


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

    html = _COMMENT_RE.sub(" ", resp.text)
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
        if len(t.split()) >= 4 and t not in seen:
            seen.add(t)
            deduped.append((h, t))
    return FetchedDocument(url=url, status_code=resp.status_code, sections=deduped)
