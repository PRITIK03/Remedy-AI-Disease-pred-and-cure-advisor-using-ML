"""Document parsing engine for medical reports (Phase 7).

Extracts clean text from text-based PDFs deterministically using pypdf.
Renders pages as base64 images using pypdfium2/Pillow for scanned PDFs and image files.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Literal

import pypdf
import pypdfium2
from PIL import Image

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("backend.reports.parser")


class DocumentParseError(Exception):
    """Raised when document cannot be parsed or exceeds safety limits."""


@dataclass
class ParsedDocument:
    kind: Literal["text", "multimodal"]
    text_content: str | None = None
    images: list[dict[str, str]] | None = None  # [{"mime_type": "...", "data": "base64..."}]
    page_count: int = 1


def inspect_and_validate_file(file_bytes: bytes, filename: str) -> str:
    """Validate magic bytes and return canonical mime type."""
    settings = get_settings()
    if len(file_bytes) > settings.reports_max_bytes:
        raise DocumentParseError(
            f"File size ({len(file_bytes)} bytes) exceeds limit ({settings.reports_max_bytes} bytes)"
        )

    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if file_bytes.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP":
        return "image/webp"

    raise DocumentParseError(
        "Unsupported file format. Supported: PDF, JPEG, PNG, WEBP."
    )


def parse_document(file_bytes: bytes, mime_type: str) -> ParsedDocument:
    """Parse report file into either pure text or multimodal images."""
    settings = get_settings()

    if mime_type == "application/pdf":
        return _parse_pdf(file_bytes, max_pages=settings.reports_max_pdf_pages)
    elif mime_type in ("image/jpeg", "image/png", "image/webp"):
        return _parse_image(file_bytes, mime_type)
    else:
        raise DocumentParseError(f"Unsupported MIME type: {mime_type}")


def _parse_pdf(file_bytes: bytes, max_pages: int = 10) -> ParsedDocument:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        raise DocumentParseError(f"Corrupt or unreadable PDF document: {exc}") from exc

    page_count = len(reader.pages)
    if page_count == 0:
        raise DocumentParseError("PDF document has 0 pages.")
    if page_count > max_pages:
        raise DocumentParseError(
            f"PDF has {page_count} pages, exceeding the maximum allowed limit of {max_pages} pages."
        )

    extracted_texts: list[str] = []
    for i in range(min(page_count, max_pages)):
        try:
            page_text = reader.pages[i].extract_text() or ""
            extracted_texts.append(page_text.strip())
        except Exception:
            extracted_texts.append("")

    combined_text = "\n\n--- Page Break ---\n\n".join(t for t in extracted_texts if t)
    clean_chars = "".join(combined_text.split())
    if len(clean_chars) >= 80:
        logger.info("PDF parsed via deterministic text extraction (%d chars)", len(clean_chars))
        return ParsedDocument(kind="text", text_content=combined_text, page_count=page_count)

    logger.info("PDF has minimal text (%d chars); rendering pages to images", len(clean_chars))
    try:
        doc = pypdfium2.PdfDocument(file_bytes)
        images: list[dict[str, str]] = []
        for i in range(min(page_count, max_pages)):
            page = doc[i]
            pil_image = page.render(scale=1.5).to_pil()
            if pil_image.width > 1600 or pil_image.height > 1600:
                pil_image.thumbnail((1600, 1600))
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG", optimize=True)
            b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
            images.append({"mime_type": "image/png", "data": b64_str})

        return ParsedDocument(kind="multimodal", images=images, page_count=page_count)
    except Exception as exc:
        raise DocumentParseError(f"Failed to render PDF pages: {exc}") from exc


def _parse_image(file_bytes: bytes, mime_type: str) -> ParsedDocument:
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            img.verify()
        with Image.open(io.BytesIO(file_bytes)) as img:
            if img.width > 2000 or img.height > 2000:
                img.thumbnail((2000, 2000))
            out_buf = io.BytesIO()
            format_name = "PNG" if mime_type == "image/png" else "JPEG"
            if img.mode not in ("RGB", "L") and format_name == "JPEG":
                img = img.convert("RGB")
            img.save(out_buf, format=format_name, quality=85)
            b64_data = base64.b64encode(out_buf.getvalue()).decode("ascii")
            actual_mime = "image/png" if format_name == "PNG" else "image/jpeg"

        return ParsedDocument(
            kind="multimodal",
            images=[{"mime_type": actual_mime, "data": b64_data}],
            page_count=1,
        )
    except Exception as exc:
        raise DocumentParseError(f"Corrupt or invalid image file: {exc}") from exc

