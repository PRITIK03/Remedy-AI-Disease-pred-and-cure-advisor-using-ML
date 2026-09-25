/**
 * TypeScript types mirroring the FastAPI schemas (source of truth:
 * backend/app/schemas/assessment.py and the OpenAPI document at /openapi.json).
 * Kept in manual sync deliberately: the contract is small and stable.
 */

/** The 13 ML input features — exact backend contract. */
export interface AssessmentCreate {
  /** Age in years (25–100). */
  age: number;
  /** 0 = female, 1 = male. */
  sex: 0 | 1;
  /** Chest pain type 0–3. */
  cp: 0 | 1 | 2 | 3;
  /** Resting blood pressure, mmHg (80–220). */
  trestbps: number;
  /** Serum cholesterol, mg/dl (100–600). */
  chol: number;
  /** Fasting blood sugar > 120 mg/dl: 1 = yes, 0 = no. */
  fbs: 0 | 1;
  /** Resting ECG result 0–2. */
  restecg: 0 | 1 | 2;
  /** Max heart rate achieved, bpm (60–220). */
  thalach: number;
  /** Exercise-induced angina: 1 = yes, 0 = no. */
  exang: 0 | 1;
  /** ST depression induced by exercise, mm (0–10). */
  oldpeak: number;
  /** Slope of the peak exercise ST segment 0–2. */
  slope: 0 | 1 | 2;
  /** Number of major vessels colored 0–4. */
  ca: 0 | 1 | 2 | 3 | 4;
  /** Thalassemia indicator 0–3. */
  thal: 0 | 1 | 2 | 3;
}

export type ProbabilityLabel = "model_estimated_probability";

/** A stored assessment returned by the API. */
export interface AssessmentResponse {
  id: string;
  model_version: string;
  selected_model: string;
  predicted_disease: boolean;
  disease_probability: number;
  probability_label: ProbabilityLabel;
  created_at: string;
  input_features: AssessmentCreate;
}

export interface AssessmentListResponse {
  items: AssessmentResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface FeatureContribution {
  feature: string;
  shap_value: number;
}

export interface ExplanationResponse {
  assessment_id: string;
  model_version: string;
  method: string;
  contributions: FeatureContribution[];
  note: string;
}

export interface HealthResponse {
  status: string;
  app_env: string;
  model_version: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  services: {
    database: string;
    redis: string;
    model: string;
  };
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
  request_id?: string | null;
}
