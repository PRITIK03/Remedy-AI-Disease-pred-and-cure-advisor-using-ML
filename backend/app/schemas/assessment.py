"""Assessment API schemas.

The request model is STRICT: all 13 features are explicitly defined with
ranges/categorical constraints mirroring the ML contract in ml/config.py.
No arbitrary dictionaries are accepted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Sex = Literal[0, 1]
Fbs = Literal[0, 1]
Exang = Literal[0, 1]
ChestPain = Literal[0, 1, 2, 3]
RestEcg = Literal[0, 1, 2]
Slope = Literal[0, 1, 2]
Ca = Literal[0, 1, 2, 3, 4]
Thal = Literal[0, 1, 2, 3]


class AssessmentCreate(BaseModel):
    """Request body for POST /api/v1/assessments.

    Semantics note: the model outputs a model-estimated probability of the
    disease class — NOT a medical diagnosis.
    """

    age: int = Field(ge=25, le=100, description="Age in years.")
    sex: Sex = Field(description="0 = female, 1 = male.")
    cp: ChestPain = Field(description="Chest pain type 0-3.")
    trestbps: int = Field(ge=80, le=220, description="Resting blood pressure (mmHg).")
    chol: int = Field(ge=100, le=600, description="Serum cholesterol (mg/dl).")
    fbs: Fbs = Field(description="Fasting blood sugar > 120 mg/dl: 1 = yes, 0 = no.")
    restecg: RestEcg = Field(description="Resting ECG result 0-2.")
    thalach: int = Field(ge=60, le=220, description="Max heart rate achieved (bpm).")
    exang: Exang = Field(description="Exercise-induced angina: 1 = yes, 0 = no.")
    oldpeak: float = Field(ge=0.0, le=10.0, description="ST depression (mm).")
    slope: Slope = Field(description="Slope of peak exercise ST segment 0-2.")
    ca: Ca = Field(description="Number of major vessels colored 0-4.")
    thal: Thal = Field(description="Thalassemia indicator 0-3.")

    @field_validator("oldpeak")
    @classmethod
    def _round_oldpeak(cls, v: float) -> float:
        return round(float(v), 2)

    model_config = {
        "extra": "forbid",  # strict: reject unknown/extra fields
        "json_schema_extra": {
        "example": {
            "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
            "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
            "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
        }
        },
    }


class AssessmentResponse(BaseModel):
    id: str = Field(description="Assessment UUID.")
    model_version: str
    selected_model: str
    predicted_disease: bool = Field(
        description="True when disease_probability >= 0.5. Model output, not a diagnosis."
    )
    disease_probability: float = Field(
        ge=0.0, le=1.0, description="Model-estimated probability of the disease class."
    )
    probability_label: Literal["model_estimated_probability"] = (
        "model_estimated_probability"
    )
    created_at: datetime
    input_features: AssessmentCreate = Field(
        description="The exact features used for this prediction."
    )
    source: str = Field(default="manual", description="'manual' or 'report'")
    report_id: str | None = Field(default=None, description="UUID of source report if ingested")



class AssessmentListResponse(BaseModel):
    items: list[AssessmentResponse]
    total: int
    limit: int
    offset: int
