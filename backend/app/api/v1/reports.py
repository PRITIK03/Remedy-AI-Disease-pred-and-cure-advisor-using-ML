"""Medical Report API endpoints (Phase 7).

Endpoints:
- POST /api/v1/reports: upload PDF/image, extract metrics with confidence and evidence.
- GET  /api/v1/reports: list user's uploaded reports.
- GET  /api/v1/reports/{id}: get details & latest extraction of a report.
- POST /api/v1/reports/{id}/confirm: submit confirmed/edited metrics to create an assessment.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from backend.app.dependencies import DbSessionDep, ModelServiceDep
from backend.app.dependencies_auth import CurrentUserDep, enforce_csrf
from backend.app.reports import service as report_service
from backend.app.reports.parser import DocumentParseError
from backend.app.reports.schemas import (
    ConfirmReportAssessmentRequest,
    MedicalReportListResponse,
    MedicalReportResponse,
)
from backend.app.schemas.assessment import AssessmentCreate, AssessmentResponse
from backend.app.services import assessment_service

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(enforce_csrf)],
)


@router.post(
    "",
    response_model=MedicalReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a medical report (PDF or image)",
)
async def upload_report(
    db: DbSessionDep,
    user: CurrentUserDep,
    file: Annotated[UploadFile, File()],
) -> MedicalReportResponse:

    """Upload a medical report, validate format and size, and extract metrics."""
    filename = file.filename or "uploaded_report"
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file data: {exc}",
        ) from exc

    try:
        report = report_service.upload_and_process_report(
            db=db,
            user_id=user.id,
            filename=filename,
            file_bytes=content,
        )
    except DocumentParseError as exc:
        raise HTTPException(
            status_code=422,  # inline: the Starlette constant is deprecated
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report processing failed: {exc}",
        ) from exc

    return report_service.to_report_response(report)


@router.get(
    "",
    response_model=MedicalReportListResponse,
    summary="List authenticated user's uploaded reports",
)
def list_reports(
    db: DbSessionDep,
    user: CurrentUserDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MedicalReportListResponse:
    """Return paginated list of reports strictly owned by the current user."""
    items, total = report_service.get_user_reports(
        db, user_id=user.id, limit=limit, offset=offset
    )
    return MedicalReportListResponse(
        items=[report_service.to_report_response(r) for r in items],
        total=total,
    )


@router.get(
    "/{report_id}",
    response_model=MedicalReportResponse,
    summary="Retrieve report and extraction details by ID",
)
def get_report(
    report_id: UUID,
    db: DbSessionDep,
    user: CurrentUserDep,
) -> MedicalReportResponse:
    """Retrieve single report with ownership enforcement (returns 404 for missing or foreign)."""
    report = report_service.get_user_report_by_id(db, user_id=user.id, report_id=report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return report_service.to_report_response(report)


@router.post(
    "/{report_id}/confirm",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm extracted values to create a new assessment",
)
def confirm_report_assessment(
    report_id: UUID,
    payload: ConfirmReportAssessmentRequest,
    model_service: ModelServiceDep,
    db: DbSessionDep,
    user: CurrentUserDep,
) -> AssessmentResponse:
    """Validate confirmed values, verify report ownership, and run ML prediction pipeline."""
    report = report_service.get_user_report_by_id(db, user_id=user.id, report_id=report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    # Convert confirm payload to standard AssessmentCreate for ML inference
    assessment_in = AssessmentCreate(**payload.model_dump())
    row = assessment_service.create_assessment(
        db=db,
        model_service=model_service,
        payload=assessment_in,
        user_id=user.id,
        source="report",
        report_id=report.id,
    )
    return AssessmentResponse(**assessment_service.to_response(row))
