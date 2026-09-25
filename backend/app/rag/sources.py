"""Source manifest loading for the knowledge base.

rag/sources.yaml is the single declaration of what may enter the knowledge
base. Only reputable medical publishers are allowed; the manifest records
provenance for every document (title, publisher, URL, license note).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.app.core.logging import get_logger

logger = get_logger("backend.rag.sources")

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "rag" / "sources.yaml"

ALLOWED_PUBLISHER_DOMAINS: dict[str, str] = {
    # Government health organizations
    "cdc.gov": "US Centers for Disease Control and Prevention",
    "nih.gov": "US National Institutes of Health",
    "nhlbi.nih.gov": "National Heart, Lung, and Blood Institute (NIH)",
    "medlineplus.gov": "MedlinePlus (US National Library of Medicine)",
    "who.int": "World Health Organization",
    "nhs.uk": "UK National Health Service",
    # Recognized medical institutions
    "heart.org": "American Heart Association",
    "mayoclinic.org": "Mayo Clinic",
    "clevelandclinic.org": "Cleveland Clinic",
}


@dataclass(frozen=True)
class SourceRecord:
    url: str
    title: str
    publisher: str
    document_type: str
    license_note: str
    section_selectors: list[str]


class ManifestError(ValueError):
    """Raised when the manifest is missing, malformed, or untrusted."""


def load_manifest(path: Path = MANIFEST_PATH) -> list[SourceRecord]:
    """Load + validate the source manifest. Fails closed on any problem."""
    if not path.exists():
        raise ManifestError(f"Source manifest not found: {path}")
    try:
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"Manifest YAML is invalid: {exc}") from exc

    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list) or not sources:
        raise ManifestError("Manifest must contain a non-empty 'sources' list.")

    records: list[SourceRecord] = []
    seen_urls: set[str] = set()
    for i, entry in enumerate(sources):
        if not isinstance(entry, dict):
            raise ManifestError(f"Source #{i} is not a mapping.")
        missing = {"url", "title", "publisher", "document_type"} - set(entry)
        if missing:
            raise ManifestError(f"Source #{i} missing fields: {sorted(missing)}")
        url = str(entry["url"]).strip()
        if not url.startswith("https://"):
            raise ManifestError(f"Source #{i} URL must be https: {url}")
        # Host-based allowlist: exact domain or any subdomain of it
        # (e.g. www.nhlbi.nih.gov matches nhlbi.nih.gov).
        host = url.split("/", 3)[2].lower()
        host_ok = any(
            host == domain or host.endswith(f".{domain}")
            for domain in ALLOWED_PUBLISHER_DOMAINS
        )
        if not host_ok:
            raise ManifestError(
                f"Source #{i} URL is not from an allowed medical publisher: {url}"
            )
        if url in seen_urls:
            raise ManifestError(f"Duplicate source URL in manifest: {url}")
        seen_urls.add(url)
        records.append(
            SourceRecord(
                url=url,
                title=str(entry["title"]).strip(),
                publisher=str(entry["publisher"]).strip(),
                document_type=str(entry.get("document_type", "guidance")).strip(),
                license_note=str(entry.get("license_note", "")).strip(),
                section_selectors=list(entry.get("section_selectors", [])),
            )
        )
    return records
