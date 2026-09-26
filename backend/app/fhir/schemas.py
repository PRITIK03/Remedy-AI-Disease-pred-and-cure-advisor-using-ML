"""Strict Pydantic FHIR R4-shaped schemas (Phase 8).

These are *lightweight* models that mirror the FHIR R4 JSON structure for
the three resources we expose (Patient, Observation, DiagnosticReport).
They are intentionally NOT a full FHIR implementation: only the fields this
application actually populates are declared, and unknown fields are rejected
(`extra="forbid"`) so the mapper can never leak internal ORM columns.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FhirBundle(BaseModel):
    """Minimal FHIR `Bundle` (type=collection) carrying generated resources.

    A bundle (rather than a bare list) is what FHIR clients expect, and it
    gives us one place to state provenance for the whole response.
    """

    resourceType: str = Field(default="Bundle")
    type: str = Field(default="collection")
    meta: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    entry: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Primitive FHIR types
# --------------------------------------------------------------------------- #

class FhirIdentifier(BaseModel):
    """FHIR `Identifier` — used to pin `resource.id` and `subject/reference`."""

    model_config = {"extra": "forbid"}

    system: str = Field(description="Namespace for the identifier value.")
    value: str = Field(description="The identifier value itself.")


class FhirCoding(BaseModel):
    model_config = {"extra": "forbid"}

    system: str
    code: str
    display: str | None = None


class FhirCodeableConcept(BaseModel):
    model_config = {"extra": "forbid"}

    coding: list[FhirCoding] = Field(default_factory=list)
    text: str | None = None


class FhirReference(BaseModel):
    """Reference — always carries `reference` and a human-readable `display`."""

    model_config = {"extra": "forbid"}

    reference: str = Field(
        description="Literal reference, e.g. 'Patient/abc' or 'Assessment/abc'."
    )
    display: str | None = None


class FhirQuantity(BaseModel):
    model_config = {"extra": "forbid"}

    value: float
    unit: str
    system: str = "http://unitsofmeasure.org"
    code: str


class FhirPeriod(BaseModel):
    model_config = {"extra": "forbid"}

    start: str | None = None
    end: str | None = None


# --------------------------------------------------------------------------- #
# Patient
# --------------------------------------------------------------------------- #

class FhirPatient(BaseModel):
    model_config = {"extra": "forbid"}

    resourceType: Literal["Patient"] = "Patient"
    id: str
    meta: dict[str, Any] | None = None
    identifier: list[FhirIdentifier] = Field(default_factory=list)
    active: bool = True
    name: list[dict[str, Any]] = Field(default_factory=list)
    gender: Literal["male", "female", "other", "unknown"] = "unknown"
    birthDate: str | None = None


# --------------------------------------------------------------------------- #
# Observation
# --------------------------------------------------------------------------- #

class FhirObservation(BaseModel):
    model_config = {"extra": "forbid"}

    resourceType: Literal["Observation"] = "Observation"
    id: str
    meta: dict[str, Any] | None = None
    status: Literal["final", "preliminary", "amended", "cancelled"] = "final"
    category: list[FhirCodeableConcept] = Field(default_factory=list)
    code: FhirCodeableConcept
    subject: FhirReference
    effectiveDateTime: str
    issued: str | None = None
    valueQuantity: FhirQuantity | None = None
    valueString: str | None = None
    dataAbsentReason: FhirCodeableConcept | None = None
    note: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# DiagnosticReport
# --------------------------------------------------------------------------- #

class FhirDiagnosticReport(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    resourceType: Literal["DiagnosticReport"] = "DiagnosticReport"
    id: str
    meta: dict[str, Any] | None = None
    status: Literal["registered", "partial", "preliminary", "final", "amended"] = "final"
    category: list[FhirCodeableConcept] = Field(default_factory=list)
    code: FhirCodeableConcept
    subject: FhirReference
    effectiveDateTime: str
    issued: str | None = None
    result: list[FhirReference] = Field(default_factory=list)
    conclusion: str | None = None


__all__ = [
    "FhirIdentifier",
    "FhirCoding",
    "FhirCodeableConcept",
    "FhirReference",
    "FhirQuantity",
    "FhirPeriod",
    "FhirBundle",
    "FhirPatient",
    "FhirObservation",
    "FhirDiagnosticReport",
]
