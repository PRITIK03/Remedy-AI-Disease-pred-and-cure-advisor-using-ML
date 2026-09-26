"""Service orchestrating document storage, extraction, and validation (Phase 7)."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.models.report import MedicalReport, ReportExtraction, ReportStatus
from backend.app.llm.client import LLMClient, get_llm_client
from backend.app.reports.parser import (
    DocumentParseError,
    inspect_and_validate_file,
    parse_document,
)
from backend.app.reports.prompts import (
    REPORT_EXTRACTION_SYSTEM_PROMPT_V1,
    USER_REPORT_IMAGE_PROMPT,
    USER_REPORT_TEXT_PROMPT_TEMPLATE,
)
from backend.app.reports.schemas import (
    CardiovascularReportExtraction,
    MedicalReportResponse,
    ReportExtractionResponse,
)
from backend.app.storage import StorageProvider, get_storage_provider

logger = get_logger("backend.reports.service")


class ReportServiceError(Exception):
    """Base error for report operations."""


class ReportNotFoundError(ReportServiceError):
    """Report not found or not owned by user."""



def upload_and_process_report(
    db: Session,
    user_id: UUID,
    filename: str,
    file_bytes: bytes,
    storage: StorageProvider | None = None,
    llm: LLMClient | None = None,
) -> MedicalReport:
    """Validate file, save to storage, record in DB, and run extraction."""
    storage = storage or get_storage_provider()
    mime_type = inspect_and_validate_file(file_bytes, filename)
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)

    report_id = uuid.uuid4()
    storage_key = f"{user_id}/{report_id}_{filename}"
    storage.save(storage_key, file_bytes)

    report = MedicalReport(
        id=report_id,
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        file_size_bytes=file_size,
        file_hash=file_hash,
        storage_key=storage_key,
        status=ReportStatus.PROCESSING,
    )
    db.add(report)
    db.flush()

    try:
        extract_metrics_from_report(db, report, file_bytes, llm=llm)
        report.status = ReportStatus.COMPLETED
        logger.info("Report %s processed successfully", report.id)
    except Exception as exc:
        report.status = ReportStatus.FAILED
        report.error_message = str(exc)
        logger.error("Report %s extraction failed: %s", report.id, exc)

    db.flush()
    return report


def extract_metrics_from_report(
    db: Session,
    report: MedicalReport,
    file_bytes: bytes,
    llm: LLMClient | None = None,
) -> ReportExtraction:
    """Parse document and invoke LLM (text or multimodal) to extract structured features."""
    settings = get_settings()
    llm_client = llm or get_llm_client()
    model_name = settings.multimodal_model or settings.llm_model or "multimodal-extractor"

    parsed = parse_document(file_bytes, report.mime_type)

    if parsed.kind == "text" and parsed.text_content:
        user_prompt = USER_REPORT_TEXT_PROMPT_TEMPLATE.format(document_text=parsed.text_content)
        extracted_data: CardiovascularReportExtraction = llm_client.generate_structured(
            REPORT_EXTRACTION_SYSTEM_PROMPT_V1,
            user_prompt,
            CardiovascularReportExtraction,
        )
    elif parsed.kind == "multimodal" and parsed.images:
        extracted_data: CardiovascularReportExtraction = llm_client.generate_structured_multimodal(
            REPORT_EXTRACTION_SYSTEM_PROMPT_V1,
            USER_REPORT_IMAGE_PROMPT,
            parsed.images,
            CardiovascularReportExtraction,
        )
    else:
        raise DocumentParseError("Document could not be converted to text or images.")

    features: dict[str, Any] = {}
    confidences: dict[str, float] = {}
    evidence: dict[str, str] = {}

    for field_name in (
        "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
        "thalach", "exang", "oldpeak", "slope", "ca", "thal"
    ):
        field_obj = getattr(extracted_data, field_name, None)
        if field_obj is not None:
            features[field_name] = field_obj.value
            confidences[field_name] = field_obj.confidence
            evidence[field_name] = field_obj.evidence
        else:
            features[field_name] = None
            confidences[field_name] = 0.0
            evidence[field_name] = "Not found"

    extraction = ReportExtraction(
        report_id=report.id,
        extraction_model=model_name,
        prompt_version="v1",
        extracted_features=features,
        confidences=confidences,
        evidence=evidence,
        notes=extracted_data.notes or None,
    )
    db.add(extraction)
    db.flush()
    return extraction


def get_user_reports(
    db: Session,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[MedicalReport], int]:
    """Retrieve paginated reports strictly owned by user."""
    stmt = (
        select(MedicalReport)
        .where(MedicalReport.user_id == user_id)
        .order_by(desc(MedicalReport.created_at))
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt))

    count_stmt = select(func.count(MedicalReport.id)).where(MedicalReport.user_id == user_id)
    total = db.scalar(count_stmt) or 0
    return items, int(total)


def get_user_report_by_id(
    db: Session,
    user_id: UUID,
    report_id: UUID,
) -> MedicalReport | None:
    """Retrieve single report scoped strictly to user."""
    stmt = select(MedicalReport).where(
        MedicalReport.id == report_id,
        MedicalReport.user_id == user_id,
    )
    return db.scalar(stmt)


def to_report_response(report: MedicalReport) -> MedicalReportResponse:
    """Serialize MedicalReport ORM into response schema."""
    latest_ext: ReportExtractionResponse | None = None
    if report.extractions:
        sorted_exts = sorted(report.extractions, key=lambda e: e.created_at, reverse=True)
        e = sorted_exts[0]
        latest_ext = ReportExtractionResponse(
            id=e.id,
            report_id=e.report_id,
            extraction_model=e.extraction_model,
            prompt_version=e.prompt_version,
            extracted_features=e.extracted_features,
            confidences=e.confidences,
            evidence=e.evidence,
            notes=e.notes,
            created_at=e.created_at,
        )

    return MedicalReportResponse(
        id=report.id,
        filename=report.filename,
        mime_type=report.mime_type,
        file_size_bytes=report.file_size_bytes,
        file_hash=report.file_hash,
        status=report.status.value if hasattr(report.status, "value") else str(report.status),
        error_message=report.error_message,
        created_at=report.created_at,
        latest_extraction=latest_ext,
    )

