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
  ExplanationResponse,
  HealthResponse,
  ReadinessResponse,
} from "@/types/api";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  ""
);

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
      // Assessment data is sensitive; never let the browser cache it.
      cache: "no-store",
    });
    if (!res.ok) {
      let code = "http_error";
      let message = `Request failed with status ${res.status}`;
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
        }
        if (body.request_id) {
          throw new ApiError(res.status, code, message, body.request_id);
        }
      } catch (parseError) {
        if (parseError instanceof ApiError) throw parseError;
        // fall through with default message
      }
      throw new ApiError(res.status, code, message);
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

  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  getReadiness(): Promise<ReadinessResponse> {
    return request<ReadinessResponse>("/ready");
  },
};
