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
  /** Phase 7 provenance: "manual" form entry or "report" confirmed extraction. */
  source: "manual" | "report" | string;
  /** UUID of the source medical report when source === "report". */
  report_id: string | null;
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
    /** Phase 9: report storage backend health ("ok" | "unavailable"). */
    storage: string;
  };
}

/** One verified source citation returned by the guidance endpoint. */
export interface Citation {
  title: string;
  source: string;
  url: string;
  section: string;
}

/** The validated AI guidance block (see backend/app/schemas/guidance.py). */
export interface GuidanceDetail {
  summary: string;
  model_explanation: string;
  key_factors: string[];
  guidance: string[];
  when_to_seek_care: string[];
  limitations: string;
  citations: Citation[];
  evidence_count: number;
}

/** Response for POST /api/v1/assessments/{id}/guidance.

  `assessment` is the authoritative MODEL OUTPUT snapshot — the LLM cannot
  produce or alter it. `guidance` is AI-GENERATED, evidence-grounded text.
  Phase 5 adds minimal workflow metadata (the API answers 202 when review is
  required, with no guidance payload).
 */
export interface GuidanceResponse {
  assessment: {
    assessment_id: string;
    model_version: string;
    selected_model: string;
    predicted_disease: boolean;
    disease_probability: number;
  };
  guidance: GuidanceDetail;
  prompt_version: string;
  generated_at: string;
  workflow_status: "completed" | "pending_review";
  review_required: boolean;
  safety_flags?: string[];
}

/** 202 payload when the workflow flags the case for human review. */
export interface ReviewPendingDetail {
  message: string;
  review_required: true;
  workflow_status: "pending_review";
  assessment: GuidanceResponse["assessment"];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
  request_id?: string | null;
}

/** --- Phase 7: medical report ingestion ------------------------------------ */

/** One validated extraction row returned by the report API. */
export interface ReportExtractionResponse {
  id: string;
  report_id: string;
  extraction_model: string;
  prompt_version: string;
  extracted_features: Record<string, number | null>;
  confidences: Record<string, number>;
  evidence: Record<string, string>;
  notes: string | null;
  created_at: string;
}

export interface MedicalReportResponse {
  id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  file_hash: string;
  status: "pending" | "processing" | "completed" | "failed" | string;
  error_message: string | null;
  created_at: string;
  latest_extraction: ReportExtractionResponse | null;
}

export interface MedicalReportListResponse {
  items: MedicalReportResponse[];
  total: number;
}

/** Confirmed / user-edited 13-field payload used to create an assessment from a report. */
export type ConfirmReportAssessmentRequest = AssessmentCreate;

/** --- Auth (Phase 6) ------------------------------------------------------ */

/** Safe user shape — the backend NEVER returns password hashes. */
export interface UserPublic {
  id: string;
  email: string;
  display_name: string | null;
  role: "user" | "reviewer" | "admin";
  is_active: boolean;
  created_at: string;
}

/** Response of POST /api/v1/auth/register and /login (no session ids). */
export interface AuthResponse {
  user: UserPublic;
}
