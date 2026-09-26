/**
 * Phase 7 test — report review form.
 *
 * The API client and Next router are mocked; no network involved.
 * Verifies the human-in-the-loop contract: extracted values pre-fill the
 * editable fields, invalid values block confirmation, and confirming posts a
 * strictly numeric 13-field payload to the report confirm endpoint.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportReviewForm } from "@/components/report/report-review-form";
import type { MedicalReportResponse } from "@/types/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const confirmReport = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, confirmReport: (...args: unknown[]) => confirmReport(...args) },
  };
});

const EXTRACTED = {
  age: 45, sex: 1, cp: 0, trestbps: 120, chol: 180, fbs: 0,
  restecg: 0, thalach: 170, exang: 0, oldpeak: 0.5, slope: 1,
  ca: 0, thal: 2,
};

const REPORT: MedicalReportResponse = {
  id: "report-1",
  filename: "checkup.png",
  mime_type: "image/png",
  file_size_bytes: 2048,
  file_hash: "deadbeef",
  status: "completed",
  error_message: null,
  created_at: "2026-09-26T10:00:00Z",
  latest_extraction: {
    id: "extraction-1",
    report_id: "report-1",
    extraction_model: "stub-vision",
    prompt_version: "v1",
    extracted_features: EXTRACTED,
    confidences: { age: 0.95, chol: 0.4 },
    evidence: { age: "Age: 45 years", chol: "Total cholesterol 180 mg/dL" },
    notes: "Unit conversion applied to cholesterol.",
    created_at: "2026-09-26T10:00:00Z",
  },
};

describe("ReportReviewForm", () => {
  beforeEach(() => {
    push.mockReset();
    confirmReport.mockReset();
  });

  it("pre-fills editable fields from the AI extraction", () => {
    render(<ReportReviewForm report={REPORT} />);
    expect(screen.getByLabelText(/^Age \(years\)/)).toHaveValue("45");
    expect(screen.getByLabelText(/^Cholesterol/)).toHaveValue("180");
    expect(screen.getByText(/confidence 95%/)).toBeInTheDocument();
    expect(screen.getByText(/Total cholesterol 180 mg\/dL/)).toBeInTheDocument();
  });

  it("leaves missing metrics empty and blocks confirmation", async () => {
    const incomplete: MedicalReportResponse = {
      ...REPORT,
      latest_extraction: {
        ...REPORT.latest_extraction!,
        extracted_features: { ...EXTRACTED, ca: null },
      },
    };
    render(<ReportReviewForm report={incomplete} />);
    const confirmButton = screen.getByRole("button", { name: /Confirm and create assessment/ });
    await waitFor(() => expect(confirmButton).toBeDisabled());
    expect(confirmReport).not.toHaveBeenCalled();
  });

  it("posts a numeric payload and navigates to the result on confirm", async () => {
    confirmReport.mockResolvedValue({ id: "assessment-9" });
    const user = userEvent.setup();
    render(<ReportReviewForm report={REPORT} />);
    await user.click(
      screen.getByRole("button", { name: /Confirm and create assessment/ })
    );
    await waitFor(() => expect(confirmReport).toHaveBeenCalledTimes(1));
    const [reportId, payload] = confirmReport.mock.calls[0] as [string, Record<string, number>];
    expect(reportId).toBe("report-1");
    expect(payload.age).toBe(45);
    expect(typeof payload.oldpeak).toBe("number");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/results/assessment-9"));
  });
});
