/**
 * Typed API client for the Remedy-AI FastAPI backend.
 *
 * The base URL comes from NEXT_PUBLIC_API_URL (see .env.example). No fetch
 * calls scattered through components.
 */

import type {
  AssessmentCreate,
  AssessmentListResponse,
  AssessmentResponse,
  ConfirmReportAssessmentRequest,
  ExplanationResponse,
  GuidanceResponse,
  HealthResponse,
  MedicalReportListResponse,
  MedicalReportResponse,
  ReadinessResponse,
} from "@/types/api";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  ""
);

export function apiBaseUrl(): string {
  return API_URL;
}

function readCsrfHeader(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith("remedy_csrf="));
  const token = match?.split("=")[1];
  return token ? { "X-CSRF-Token": token } : {};
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15000
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
      signal: controller.signal,
      // Cookies travel with every API call (Phase 6 session auth) and
      // assessment data is sensitive; never let the browser cache it.
      credentials: "include" as RequestCredentials,
      cache: "no-store",
    });
    if (!res.ok) {
      let code = "http_error";
      let message = `Request failed with status ${res.status}`;
      let detailBody: unknown = undefined;
      try {
        const body = (await res.json()) as {
          detail?: unknown;
          error?: { code?: string; message?: string };
          request_id?: string;
        };
        if (body.error?.message) {
          code = body.error.code ?? code;
          message = body.error.message;
        } else if (typeof body.detail === "string") {
          message = body.detail;
        } else if (body.detail && typeof body.detail === "object") {
          // Structured detail (e.g. 202 review-pending payload from the
          // guidance workflow): carried on the error for callers to inspect.
          detailBody = body.detail;
          const d = body.detail as { message?: string };
          if (typeof d.message === "string") message = d.message;
          code = "structured_detail";
        }
        if (body.request_id) {
          throw new ApiError(res.status, code, message, body.request_id);
        }
      } catch (parseError) {
        if (parseError instanceof ApiError) throw parseError;
        // fall through with default message
      }
      const err = new ApiError(res.status, code, message);
      (err as ApiError & { detail?: unknown }).detail = detailBody;
      throw err;
    }
    return (await res.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "timeout", "The request timed out. Please try again.");
    }
    throw new ApiError(0, "network_error", "Cannot reach the server. Is the backend running?");
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  /** Exposed for auth helpers (CSRF bootstrap) and tests. */
  baseUrl: apiBaseUrl,

  createAssessment(payload: AssessmentCreate): Promise<AssessmentResponse> {
    return request<AssessmentResponse>("/api/v1/assessments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getAssessment(id: string): Promise<AssessmentResponse> {
    return request<AssessmentResponse>(`/api/v1/assessments/${encodeURIComponent(id)}`);
  },

  listAssessments(limit = 20, offset = 0): Promise<AssessmentListResponse> {
    return request<AssessmentListResponse>(
      `/api/v1/assessments?limit=${limit}&offset=${offset}`
    );
  },

  getExplanation(id: string): Promise<ExplanationResponse> {
    return request<ExplanationResponse>(
      `/api/v1/assessments/${encodeURIComponent(id)}/explanation`
    );
  },

  // Explicit user request only — never called automatically on render.
  // Long timeout: retrieval + LLM generation can take a while.
  getGuidance(id: string): Promise<GuidanceResponse> {
    return request<GuidanceResponse>(
      `/api/v1/assessments/${encodeURIComponent(id)}/guidance`,
      { method: "POST" },
      45000
    );
  },

  /** Phase 7: upload a medical report (multipart/form-data). */
  uploadReport(file: File): Promise<MedicalReportResponse> {
    const fd = new FormData();
    fd.append("file", file);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    return fetch(`${apiBaseUrl()}/api/v1/reports`, {
      method: "POST",
      body: fd,
      // CSRF token must be echoed manually because Content-Type is multipart.
      headers: readCsrfHeader(),
      credentials: "include" as RequestCredentials,
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (res) => {
        clearTimeout(timer);
        if (!res.ok) {
          let message = `Upload failed with status ${res.status}`;
          try {
            const body = (await res.json()) as { detail?: unknown };
            if (typeof body.detail === "string") message = body.detail;
          } catch {
            /* keep default */
          }
          throw new ApiError(res.status, "upload_error", message);
        }
        return (await res.json()) as MedicalReportResponse;
      })
      .catch((error: unknown) => {
        clearTimeout(timer);
        if (error instanceof ApiError) throw error;
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new ApiError(0, "timeout", "The upload timed out. Please try again.");
        }
        throw new ApiError(0, "network_error", "Cannot reach the server. Is the backend running?");
      });
  },

  listReports(limit = 20, offset = 0): Promise<MedicalReportListResponse> {
    return request<MedicalReportListResponse>(
      `/api/v1/reports?limit=${limit}&offset=${offset}`
    );
  },

  getReport(id: string): Promise<MedicalReportResponse> {
    return request<MedicalReportResponse>(`/api/v1/reports/${encodeURIComponent(id)}`);
  },

  confirmReport(id: string, payload: ConfirmReportAssessmentRequest): Promise<AssessmentResponse> {
    return request<AssessmentResponse>(
      `/api/v1/reports/${encodeURIComponent(id)}/confirm`,
      { method: "POST", body: JSON.stringify(payload) },
      30000
    );
  },

  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  getReadiness(): Promise<ReadinessResponse> {
    return request<ReadinessResponse>("/ready");
  },
};
