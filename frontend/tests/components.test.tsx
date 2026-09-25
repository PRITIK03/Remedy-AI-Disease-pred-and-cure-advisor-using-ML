import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProbabilityGauge } from "@/components/results/probability-gauge";
import { ContributionsList } from "@/components/results/contributions-list";
import { HistoryCards } from "@/components/history/history-cards";
import type { AssessmentResponse } from "@/types/api";

const MOCK_ASSESSMENT: AssessmentResponse = {
  id: "abc",
  model_version: "2.0.0",
  selected_model: "logistic_regression",
  predicted_disease: false,
  disease_probability: 0.3483,
  probability_label: "model_estimated_probability",
  created_at: "2026-09-25T10:00:00Z",
  input_features: {
    age: 45, sex: 1, cp: 0, trestbps: 120, chol: 180, fbs: 0,
    restecg: 0, thalach: 170, exang: 0, oldpeak: 0.5, slope: 1,
    ca: 0, thal: 2,
  },
};

describe("ProbabilityGauge", () => {
  it("renders the probability percentage", () => {
    render(<ProbabilityGauge probability={0.3483} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("34.8%")
    );
  });

  it("clamps out-of-range probabilities", () => {
    render(<ProbabilityGauge probability={1.7} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("100.0%")
    );
  });
});

describe("ContributionsList", () => {
  it("shows loading skeletons while pending", () => {
    render(<ContributionsList contributions={null} loading />);
    expect(screen.getByLabelText(/loading feature contributions/i)).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    const { getByText } = render(
      <ContributionsList
        contributions={null}
        loading={false}
        error="Explanation service unavailable"
        onRetry={() => {}}
      />
    );
    expect(getByText(/explanation service unavailable/i)).toBeInTheDocument();
    expect(getByText(/retry/i)).toBeInTheDocument();
  });

  it("renders contribution bars with model-contribution framing", () => {
    render(
      <ContributionsList
        loading={false}
        contributions={[
          { feature: "numeric__oldpeak", shap_value: 0.65 },
          { feature: "categorical__ca_0", shap_value: -0.57 },
        ]}
      />
    );
    expect(screen.getByText("ST depression")).toBeInTheDocument();
    expect(screen.getByText("0 affected vessels")).toBeInTheDocument();
    expect(screen.getByText("+0.650")).toBeInTheDocument();
    expect(screen.getByText("-0.570")).toBeInTheDocument();
  });
});

describe("HistoryCards", () => {
  it("renders probability, classification and model version", () => {
    render(<HistoryCards items={[MOCK_ASSESSMENT]} />);
    expect(screen.getByText(/34.8%/)).toBeInTheDocument();
    expect(screen.getByText(/lower probability/i)).toBeInTheDocument();
    expect(screen.getByText(/v2.0.0/)).toBeInTheDocument();
  });
});
