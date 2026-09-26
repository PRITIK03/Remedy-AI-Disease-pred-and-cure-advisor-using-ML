"""FHIR mapper — application data → Patient / Observation / DiagnosticReport.

Phase 8. Design rules (all deliberate):

1. **Nothing is invented.** Only fields already stored by the application are
   emitted. A missing value becomes `dataAbsentReason`, never a guess.
2. **No internal columns leak.** The mapper reads through the service-level
   response dicts (`assessment_service.to_response`, `report_service
   .to_report_response`) and the `User.to_public()` projection, so ORM
   internals (password hashes, storage keys, raw evidence text) can never
   reach a FHIR payload.
3. **Provenance is explicit.** Every resource carries `meta.source` +
   a `generated` tag, so a consumer can tell this apart from EHR data.
4. **The ML output is not a clinical measurement.** The disease probability is
   emitted as an Observation with an explicit
   `model_estimated_probability` label and an interpretation note.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.app.fhir.resources import (
    ASSESSMENT_CATEGORY_CODING,
    CATEGORICAL_FEATURES,
    DIAGNOSTIC_REPORT_CODE,
    FEATURE_OBSERVATION_MAP,
    LOCAL_ASSESSMENT,
    categorical_display,
    meta_tag,
)
from backend.app.fhir.schemas import (
    FhirCodeableConcept,
    FhirCoding,
    FhirDiagnosticReport,
    FhirIdentifier,
    FhirObservation,
    FhirPatient,
    FhirQuantity,
    FhirReference,
)

#: The 13 model inputs, in the canonical order used by the ML pipeline.
FEATURE_ORDER = (
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
)

#: Feature order used for Observation ids so the resources sort deterministically.
_OBSERVATION_IDX = {name: i for i, name in enumerate(FEATURE_ORDER)}


def _iso(value: datetime | str | None = None) -> str:
    """Normalize a datetime to a FHIR `dateTime` string (UTC, ISO-8601)."""
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _observation_id(assessment_id: str, feature: str) -> str:
    return f"{assessment_id}-{_OBSERVATION_IDX[feature]}"


def patient_reference(user_id: UUID | str) -> FhirReference:
    return FhirReference(
        reference=f"Patient/{user_id}",
        display="Remedy-AI account holder",
    )


# --------------------------------------------------------------------------- #
# Patient
# --------------------------------------------------------------------------- #

def map_patient(user_public: dict[str, Any]) -> FhirPatient:
    """Map the authenticated user's public projection to a FHIR Patient.

    Deliberately minimal: the application stores a display name and an email
    (an account identifier, not a clinical contact point), and the sex of the
    *assessed subject* is per-assessment, not a patient attribute we can
    assert. So `gender` stays "unknown" and no email/contact is emitted.
    """
    user_id = str(user_public["id"])
    meta = meta_tag(None)
    meta["tag"].append(  # type: ignore[union-attr]
        {
            "system": LOCAL_ASSESSMENT,
            "code": "demographics-minimal",
            "display": (
                "Only account-level demographics are exported; no clinical "
                "patient record exists in Remedy-AI."
            ),
        }
    )
    names: list[dict[str, Any]] = []
    display_name = user_public.get("display_name")
    if display_name:
        names.append({"use": "usual", "text": str(display_name)})
    return FhirPatient(
        id=user_id,
        meta=meta,
        identifier=[
            FhirIdentifier(system=str(meta["source"]), value=user_id),
        ],
        active=bool(user_public.get("is_active", True)),
        name=names,
        gender="unknown",
        birthDate=None,
    )


# --------------------------------------------------------------------------- #
# Observations
# --------------------------------------------------------------------------- #

def _category() -> list[FhirCodeableConcept]:
    return [
        FhirCodeableConcept(
            coding=[FhirCoding(**ASSESSMENT_CATEGORY_CODING)],
            text=ASSESSMENT_CATEGORY_CODING["display"],
        )
    ]


def _provenance_note(text: str) -> list[dict[str, Any]]:
    return [{"text": text}]


def map_feature_observations(
    assessment: dict[str, Any], user_id: UUID | str
) -> list[FhirObservation]:
    """One Observation per ML input feature (13 total), in canonical order.

    Numeric features become `valueQuantity` with a UCUM unit; categorical
    encodings become `valueString` labelled as model categories. Nothing is
    defaulted or imputed: a `None` feature yields `dataAbsentReason`.
    """
    assessment_id = str(assessment["id"])
    subject = patient_reference(user_id)
    features: dict[str, Any] = dict(assessment.get("input_features") or {})
    created = _iso(assessment.get("created_at"))
    observations: list[FhirObservation] = []

    for feature in FEATURE_ORDER:
        system, code, display, unit, unit_code = FEATURE_OBSERVATION_MAP[feature]
        value = features.get(feature)

        obs = FhirObservation(
            id=_observation_id(assessment_id, feature),
            meta=meta_tag(created),
            status="final",
            category=_category(),
            code=FhirCodeableConcept(
                coding=[FhirCoding(system=system, code=code, display=display)],
                text=display,
            ),
            subject=subject,
            effectiveDateTime=created,
            issued=created,
            note=_provenance_note(
                f"Source: user-entered or report-extracted assessment input "
                f"for {assessment_id} (model feature '{feature}')."
            ),
        )

        if value is None:
            obs.dataAbsentReason = FhirCodeableConcept(
                coding=[
                    FhirCoding(
                        system="http://terminology.hl7.org/CodeSystem/data-absent-reason",
                        code="not-performed",
                        display="Not available in the source application",
                    )
                ],
                text="No value stored for this input.",
            )
        elif feature in CATEGORICAL_FEATURES:
            obs.valueString = categorical_display(feature, int(value))
        else:
            obs.valueQuantity = FhirQuantity(
                value=float(value), unit=unit, system="http://unitsofmeasure.org",
                code=unit_code,
            )
        observations.append(obs)

    return observations


def map_probability_observation(
    assessment: dict[str, Any], user_id: UUID | str
) -> FhirObservation:
    """The model output as an Observation — explicitly NOT a diagnosis."""
    assessment_id = str(assessment["id"])
    created = _iso(assessment.get("created_at"))
    probability = float(assessment["disease_probability"])
    return FhirObservation(
        id=f"{assessment_id}-probability",
        meta=meta_tag(created),
        status="final",
        category=_category(),
        code=FhirCodeableConcept(
            coding=[
                FhirCoding(
                    system=LOCAL_ASSESSMENT,
                    code="model-estimated-disease-probability",
                    display="Model-estimated probability of disease class",
                )
            ],
            text="Model-estimated probability of disease class",
        ),
        subject=patient_reference(user_id),
        effectiveDateTime=created,
        issued=created,
        valueQuantity=FhirQuantity(
            value=probability,
            unit="1",
            system="http://unitsofmeasure.org",
            code="1",
        ),
        note=_provenance_note(
            f"{assessment.get('probability_label', 'model_estimated_probability')}; "
            f"model_version={assessment.get('model_version')}; "
            f"selected_model={assessment.get('selected_model')}. "
            "Educational prototype output — not a diagnosis and not a "
            "clinically validated risk score."
        ),
    )


# --------------------------------------------------------------------------- #
# DiagnosticReport
# --------------------------------------------------------------------------- #

def map_assessment_diagnostic_report(
    assessment: dict[str, Any], user_id: UUID | str
) -> FhirDiagnosticReport:
    """Wrap one assessment (its 13 inputs + model output) as a FHIR report."""
    assessment_id = str(assessment["id"])
    created = _iso(assessment.get("created_at"))
    results = [
        FhirReference(
            reference=f"Observation/{_observation_id(assessment_id, feature)}",
            display=FEATURE_OBSERVATION_MAP[feature][2],
        )
        for feature in FEATURE_ORDER
    ]
    results.append(
        FhirReference(
            reference=f"Observation/{assessment_id}-probability",
            display="Model-estimated probability of disease class",
        )
    )
    return FhirDiagnosticReport(
        id=assessment_id,
        meta=meta_tag(created),
        status="final",
        category=_category(),
        code=FhirCodeableConcept(
            coding=[FhirCoding(**DIAGNOSTIC_REPORT_CODE)],
            text=DIAGNOSTIC_REPORT_CODE["display"],
        ),
        subject=patient_reference(user_id),
        effectiveDateTime=created,
        issued=created,
        result=results,
        conclusion=(
            f"Remedy-AI model version {assessment.get('model_version')} "
            f"(selected model: {assessment.get('selected_model')}) returned a "
            f"model-estimated probability of "
            f"{float(assessment['disease_probability']):.5f}. Input source: "
            f"{assessment.get('source', 'manual')}. Educational prototype — "
            "not a diagnosis."
        ),
    )


def map_uploaded_report_diagnostic_report(
    report: dict[str, Any], user_id: UUID | str
) -> FhirDiagnosticReport:
    """Wrap an uploaded medical report + its extraction as a FHIR report.

    Only *document metadata and extraction provenance* are exported — never
    the stored file, the storage key, the SHA-256 hash, or the raw evidence
    text (those are internal and not clinically meaningful).
    """
    report_id = str(report["id"])
    created = _iso(report.get("created_at"))
    extraction = report.get("latest_extraction") or {}
    results: list[FhirReference] = []
    conclusion_bits = [
        f"Uploaded document '{report['filename']}' ({report['mime_type']}).",
        f"Extraction status: {report.get('status')}.",
    ]
    if extraction:
        results = [
            FhirReference(
                reference=f"Observation/{report_id}-{_OBSERVATION_IDX[feature]}",
                display=FEATURE_OBSERVATION_MAP[feature][2],
            )
            for feature in FEATURE_ORDER
            if extraction.get("extracted_features", {}).get(feature) is not None
        ]
        conclusion_bits.append(
            f"Extraction model {extraction.get('extraction_model')} "
            f"(prompt {extraction.get('prompt_version')}) proposed "
            f"{len(results)} of 13 metrics, each requiring human confirmation "
            "before any prediction was produced."
        )
    return FhirDiagnosticReport(
        id=report_id,
        meta=meta_tag(created),
        status="final" if report.get("status") == "completed" else "partial",
        category=_category(),
        code=FhirCodeableConcept(
            coding=[
                FhirCoding(
                    system=LOCAL_ASSESSMENT,
                    code="uploaded-medical-report",
                    display="Uploaded medical report with AI-assisted extraction",
                )
            ],
            text="Uploaded medical report with AI-assisted extraction",
        ),
        subject=patient_reference(user_id),
        effectiveDateTime=created,
        issued=created,
        result=results,
        conclusion=" ".join(conclusion_bits),
    )


def map_report_observations(
    report: dict[str, Any], user_id: UUID | str
) -> list[FhirObservation]:
    """Observations for the *extracted* metrics of an uploaded report.

    Emitted with `status="preliminary"`: these are unconfirmed AI extractions,
    not measurements. A field the extractor could not determine becomes
    `dataAbsentReason` (never a placeholder value).
    """
    report_id = str(report["id"])
    extraction = report.get("latest_extraction") or {}
    features: dict[str, Any] = dict(extraction.get("extracted_features") or {})
    confidences: dict[str, Any] = dict(extraction.get("confidences") or {})
    created = _iso(report.get("created_at"))
    observations: list[FhirObservation] = []
    for feature in FEATURE_ORDER:
        system, code, display, unit, unit_code = FEATURE_OBSERVATION_MAP[feature]
        value = features.get(feature)
        confidence = confidences.get(feature)
        note = "AI-extracted from uploaded document; requires human confirmation."
        if isinstance(confidence, (int, float)):
            note = (
                f"AI-extracted from uploaded document (confidence "
                f"{float(confidence):.2f}); requires human confirmation."
            )
        obs = FhirObservation(
            id=f"{report_id}-{_OBSERVATION_IDX[feature]}",
            meta=meta_tag(created),
            status="preliminary",
            category=_category(),
            code=FhirCodeableConcept(
                coding=[FhirCoding(system=system, code=code, display=display)],
                text=display,
            ),
            subject=patient_reference(user_id),
            effectiveDateTime=created,
            issued=created,
            note=_provenance_note(note),
        )
        if value is None:
            obs.dataAbsentReason = FhirCodeableConcept(
                coding=[
                    FhirCoding(
                        system="http://terminology.hl7.org/CodeSystem/data-absent-reason",
                        code="not-performed",
                        display="Not found in the uploaded document",
                    )
                ],
                text="No value extracted for this input.",
            )
        elif feature in CATEGORICAL_FEATURES:
            obs.valueString = categorical_display(feature, int(value))
        else:
            obs.valueQuantity = FhirQuantity(
                value=float(value), unit=unit,
                system="http://unitsofmeasure.org", code=unit_code,
            )
        observations.append(obs)
    return observations


__all__ = [
    "FEATURE_ORDER",
    "patient_reference",
    "map_patient",
    "map_feature_observations",
    "map_probability_observation",
    "map_assessment_diagnostic_report",
    "map_uploaded_report_diagnostic_report",
    "map_report_observations",
]



