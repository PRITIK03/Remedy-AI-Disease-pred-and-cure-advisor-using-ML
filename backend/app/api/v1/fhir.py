"""Read-only FHIR R4 endpoints (Phase 8).

    GET /api/v1/fhir/assessments/{id}   → DiagnosticReport + Observations
    GET /api/v1/fhir/reports/{id}        → DiagnosticReport + Observations

Security mirrors the rest of the API exactly: a session is required, and the
underlying service performs the ownership check, so a foreign or missing id
yields the SAME 404 (no existence oracle). Nothing is written and nothing is
invented — the payloads are a serialization of data the user already stored.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.dependencies import DbSessionDep
from backend.app.dependencies_auth import CurrentUserDep, enforce_csrf
from backend.app.fhir import mapper
from backend.app.fhir.resources import GENERATED_TAG, META_SOURCE
from backend.app.fhir.schemas import FhirBundle
from backend.app.reports import service as report_service
from backend.app.services import assessment_service

router = APIRouter(
    prefix="/fhir",
    tags=["fhir"],
    dependencies=[Depends(enforce_csrf)],
)


def _entry(resource: BaseModel) -> dict[str, Any]:
    return {"resource": resource.model_dump(exclude_none=True)}


def _bundle(patient: BaseModel, others: list[BaseModel]) -> FhirBundle:
    from backend.app.fhir.resources import bundle_timestamp

    resources = [patient, *others]
    return FhirBundle(
        meta={
            "source": META_SOURCE,
            "tag": [
                {
                    "system": META_SOURCE,
                    "code": "generated",
                    "display": GENERATED_TAG,
                }
            ],
        },
        timestamp=bundle_timestamp(),
        entry=[_entry(r) for r in resources],
    )


@router.get(
    "/assessments/{assessment_id}",
    response_model=FhirBundle,
    summary="FHIR view of ONE of YOUR assessments",
    responses={404: {"description": "Assessment not found"}},
)
def fhir_assessment(
    assessment_id: UUID, db: DbSessionDep, user: CurrentUserDep
) -> FhirBundle:
    row = assessment_service.get_assessment_for_user(db, assessment_id, user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )
    assessment = assessment_service.to_response(row)
    patient = mapper.map_patient(user.to_public())
    observations = mapper.map_feature_observations(assessment, user.id)
    probability = mapper.map_probability_observation(assessment, user.id)
    report = mapper.map_assessment_diagnostic_report(assessment, user.id)
    return _bundle(patient, [*observations, probability, report])


@router.get(
    "/reports/{report_id}",
    response_model=FhirBundle,
    summary="FHIR view of ONE of YOUR uploaded medical reports",
    responses={404: {"description": "Report not found"}},
)
def fhir_report(
    report_id: UUID, db: DbSessionDep, user: CurrentUserDep
) -> FhirBundle:
    row = report_service.get_user_report_by_id(db, user_id=user.id, report_id=report_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    report = report_service.to_report_response(row)
    patient = mapper.map_patient(user.to_public())
    observations = mapper.map_report_observations(report, user.id)
    diagnostic_report = mapper.map_uploaded_report_diagnostic_report(report, user.id)
    return _bundle(patient, [*observations, diagnostic_report])
