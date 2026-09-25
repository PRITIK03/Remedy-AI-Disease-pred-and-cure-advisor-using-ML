/**
 * Zod validation mirroring the backend Pydantic schema
 * (backend/app/schemas/assessment.py). The backend remains the final
 * authority; this exists for fast, accessible UX feedback.
 */

import { z } from "zod";

const intField = (label: string, min: number, max: number) =>
  z.coerce
    .number({ message: `${label} is required` })
    .int(`${label} must be a whole number`)
    .min(min, `${label} must be at least ${min}`)
    .max(max, `${label} must be at most ${max}`);

const floatField = (label: string, min: number, max: number) =>
  z.coerce
    .number({ message: `${label} is required` })
    .min(min, `${label} must be at least ${min}`)
    .max(max, `${label} must be at most ${max}`);

const choice = <T extends readonly [number, ...number[]]>(values: T) =>
  z.coerce
    .number({ message: "Please select an option" })
    .refine((v) => (values as readonly number[]).includes(v), {
      message: "Please select a valid option",
    })
    .transform((v) => v as T[number]);

export const assessmentSchema = z.object({
  age: intField("Age", 25, 100),
  sex: choice([0, 1] as const),
  cp: choice([0, 1, 2, 3] as const),
  trestbps: intField("Resting blood pressure", 80, 220),
  chol: intField("Cholesterol", 100, 600),
  fbs: choice([0, 1] as const),
  restecg: choice([0, 1, 2] as const),
  thalach: intField("Maximum heart rate", 60, 220),
  exang: choice([0, 1] as const),
  oldpeak: floatField("ST depression", 0, 10),
  slope: choice([0, 1, 2] as const),
  ca: choice([0, 1, 2, 3, 4] as const),
  thal: choice([0, 1, 2, 3] as const),
});

export type AssessmentFormValues = z.infer<typeof assessmentSchema>;

export type FieldErrors = Partial<Record<keyof AssessmentFormValues, string>>;

/** Validate and return either the parsed values or per-field messages. */
export function validateAssessment(
  values: Record<string, unknown>
): { ok: true; data: AssessmentFormValues } | { ok: false; errors: FieldErrors } {
  const result = assessmentSchema.safeParse(values);
  if (result.success) {
    return { ok: true, data: result.data };
  }
  const errors: FieldErrors = {};
  for (const issue of result.error.issues) {
    const key = issue.path[0] as keyof AssessmentFormValues | undefined;
    if (key && !errors[key]) {
      errors[key] = issue.message;
    }
  }
  return { ok: false, errors };
}
