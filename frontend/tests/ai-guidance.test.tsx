/**
 * Phase 4 test — AI guidance rendering with backend-returned citations.
 * The API client is mocked; no network and no LLM involved.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiGuidance } from "@/components/results/ai-guidance";
import { ApiError } from "@/lib/api";

const MOCK_GUIDANCE = {
  assessment: {
    assessment_id: "abc",
    model_version: "2.0.0",
    selected_model: "logistic_regression",
    predicted_disease: false,
    disease_probability: 0.3483,
  },
  guidance: {
    summary: "The model estimated a low probability of disease.",
    model_explanation: "Age and cholesterol influenced the estimate most.",
    key_factors: ["age", "cholesterol"],
    guidance: ["Regular aerobic activity supports heart health."],
    when_to_seek_care: ["Persistent chest discomfort warrants medical review."],
    limitations: "Educational prototype; small training dataset.",
    citations: [
      {
        title: "Atherosclerosis",
        source: "UK National Health Service",
        url: "https://www.nhs.uk/conditions/atherosclerosis/",
        section: "Causes",
      },
    ],
    evidence_count: 3,
  },
  prompt_version: "v1",
  generated_at: "2026-09-26T10:00:00Z",
};

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getGuidance: vi.fn(),
    },
  };
});

import { api } from "@/lib/api";

const mockedGetGuidance = vi.mocked(api.getGuidance);

beforeEach(() => {
  mockedGetGuidance.mockReset();
});

describe("AiGuidance", () => {
  it("does not call the API until the user expands the panel", async () => {
    mockedGetGuidance.mockResolvedValue(MOCK_GUIDANCE);
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    expect(mockedGetGuidance).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    await waitFor(() => expect(mockedGetGuidance).toHaveBeenCalledTimes(1));
  });

  it("shows loading state, then summary and sections", async () => {
    let resolveApi!: (v: typeof MOCK_GUIDANCE) => void;
    mockedGetGuidance.mockReturnValue(
      new Promise((resolve) => (resolveApi = resolve))
    );
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/loading evidence/i);

    resolveApi(MOCK_GUIDANCE);
    await waitFor(() =>
      expect(screen.getByText("The model estimated a low probability of disease.")).toBeInTheDocument()
    );
    // Section headings render.
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("General guidance")).toBeInTheDocument();
    expect(screen.getByText("When to seek professional care")).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("renders citations as links pointing to the backend-returned URL", async () => {
    mockedGetGuidance.mockResolvedValue(MOCK_GUIDANCE);
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    const link = await screen.findByRole("link", { name: /Atherosclerosis/i });
    expect(link).toHaveAttribute(
      "href",
      "https://www.nhs.uk/conditions/atherosclerosis/"
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // Publisher + section displayed next to the title.
    expect(screen.getByText(/UK National Health Service/)).toBeInTheDocument();
    expect(screen.getByText(/Causes/)).toBeInTheDocument();
  });

  it("shows an error with retry when the provider fails (502)", async () => {
    mockedGetGuidance.mockRejectedValue(
      new ApiError(502, "guidance_failed", "AI guidance is temporarily unavailable.")
    );
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();

    // Retry is offered for retriable failures and calls the API again.
    mockedGetGuidance.mockResolvedValue(MOCK_GUIDANCE);
    await user.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(mockedGetGuidance).toHaveBeenCalledTimes(2));
  });

  it("shows a not-configured message on 503 without retry", async () => {
    mockedGetGuidance.mockRejectedValue(
      new ApiError(503, "not_configured", "AI guidance is not configured on this server.")
    );
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    expect(await screen.findByText(/not configured on this server/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("labels the block as AI-generated and not a diagnosis", async () => {
    mockedGetGuidance.mockResolvedValue(MOCK_GUIDANCE);
    const user = userEvent.setup();
    render(<AiGuidance assessmentId="abc" modelProbability={0.35} />);

    await user.click(screen.getByRole("button", { name: /AI Health Guidance/i }));
    expect(
      await screen.findByText(/AI-generated guidance grounded in retrieved sources/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/not a diagnosis/i)).toBeInTheDocument();
  });
});
