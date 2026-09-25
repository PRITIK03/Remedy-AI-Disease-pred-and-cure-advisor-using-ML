import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";
import type { AssessmentCreate, AssessmentResponse } from "@/types/api";

const VALID_INPUT: AssessmentCreate = {
  age: 45, sex: 1, cp: 0, trestbps: 120, chol: 180, fbs: 0,
  restecg: 0, thalach: 170, exang: 0, oldpeak: 0.5, slope: 1,
  ca: 0, thal: 2,
};

const VALID_RESPONSE: AssessmentResponse = {
  id: "123e4567-e89b-12d3-a456-426614174000",
  model_version: "2.0.0",
  selected_model: "logistic_regression",
  predicted_disease: false,
  disease_probability: 0.3483,
  probability_label: "model_estimated_probability",
  created_at: "2026-09-25T10:00:00Z",
  input_features: VALID_INPUT,
};

describe("API client", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify(VALID_RESPONSE), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          })
        )
      )
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("createAssessment posts to /api/v1/assessments with JSON body", async () => {
    await api.createAssessment(VALID_INPUT);
    const mockFetch = vi.mocked(fetch);
    const [url, init] = mockFetch.mock.calls[0];
    expect(String(url)).toContain("/api/v1/assessments");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({ age: 45 });
  });

  it("surfaces backend error messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: "internal_error", message: "An unexpected error occurred." },
            }),
            { status: 500 }
          )
        )
      )
    );
    await expect(api.getAssessment("x")).rejects.toMatchObject({
      status: 500,
      code: "internal_error",
    });
  });

  it("converts network failures into friendly ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch")))
    );
    await expect(api.getHealth()).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });

  it("times out slow requests", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError"))
            );
          })
      )
    );
    const assertion = expect(api.getReadiness()).rejects.toMatchObject({
      code: "timeout",
    });
    await vi.advanceTimersByTimeAsync(15000);
    await assertion;
    vi.useRealTimers();
  }, 10000);

  it("listAssessments builds pagination query", async () => {
    await api.listAssessments(10, 20);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("limit=10");
    expect(String(url)).toContain("offset=20");
  });

  it("getExplanation hits the explanation endpoint", async () => {
    await api.getExplanation("abc");
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/explanation");
  });

  it("ApiError instances carry structured context", () => {
    const err = new ApiError(404, "not_found", "Assessment not found", "req-1");
    expect(err.status).toBe(404);
    expect(err.code).toBe("not_found");
    expect(err.requestId).toBe("req-1");
  });
});
