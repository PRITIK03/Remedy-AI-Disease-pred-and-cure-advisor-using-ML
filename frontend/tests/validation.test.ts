import { describe, expect, it } from "vitest";

import { validateAssessment } from "@/lib/validation";
import { prettyFeatureName } from "@/lib/labels";

const VALID = {
  age: 45, sex: 1, cp: 0, trestbps: 120, chol: 180, fbs: 0,
  restecg: 0, thalach: 170, exang: 0, oldpeak: 0.5, slope: 1,
  ca: 0, thal: 2,
};

describe("assessment validation (mirrors backend schema)", () => {
  it("accepts a fully valid payload", () => {
    const result = validateAssessment(VALID);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.age).toBe(45);
      expect(result.data.oldpeak).toBeCloseTo(0.5);
    }
  });

  it("rejects age below the backend minimum", () => {
    const result = validateAssessment({ ...VALID, age: 10 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.age).toMatch(/at least 25/);
  });

  it("rejects blood pressure above the backend maximum", () => {
    const result = validateAssessment({ ...VALID, trestbps: 999 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.trestbps).toMatch(/at most 220/);
  });

  it("rejects invalid categorical values", () => {
    const result = validateAssessment({ ...VALID, cp: 7 });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.cp).toBeDefined();
  });

  it("rejects non-numeric input", () => {
    const result = validateAssessment({ ...VALID, chol: "abc" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.chol).toBeDefined();
  });

  it("reports multiple field errors at once", () => {
    const result = validateAssessment({ ...VALID, age: 5, thalach: 500 });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.age).toBeDefined();
      expect(result.errors.thalach).toBeDefined();
    }
  });

  it("coerces numeric strings from form inputs", () => {
    const result = validateAssessment({
      ...VALID,
      age: "52",
      oldpeak: "1.5",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.age).toBe(52);
      expect(result.data.oldpeak).toBeCloseTo(1.5);
    }
  });
});

describe("feature label mapping", () => {
  it("maps transformed names to readable labels", () => {
    expect(prettyFeatureName("numeric__oldpeak")).toBe("ST depression");
    expect(prettyFeatureName("categorical__cp_0")).toBe("Chest pain: typical angina");
  });

  it("passes through unknown names unchanged", () => {
    expect(prettyFeatureName("mystery__x")).toBe("mystery__x");
  });
});
