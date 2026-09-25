"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertCircle, ArrowLeft, ArrowRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { NumberField, RadioField } from "@/components/assessment/form-fields";

import { api, ApiError } from "@/lib/api";
import {
  CHEST_PAIN_OPTIONS,
  REST_ECG_OPTIONS,
  SEX_OPTIONS,
  SLOPE_OPTIONS,
  THAL_OPTIONS,
  VESSEL_OPTIONS,
  YES_NO_OPTIONS,
} from "@/lib/labels";
import { validateAssessment, type FieldErrors } from "@/lib/validation";
import { cn } from "@/lib/utils";

type FormState = Record<string, string>;

const EMPTY_FORM: FormState = {
  age: "", sex: "", cp: "", trestbps: "", chol: "", fbs: "",
  restecg: "", thalach: "", exang: "", oldpeak: "", slope: "",
  ca: "", thal: "",
};

interface StepDefinition {
  title: string;
  description: string;
  fields: string[];
  render: (props: FieldProps) => React.ReactNode;
}

interface FieldProps {
  values: FormState;
  errors: FieldErrors;
  setValue: (name: string, value: string) => void;
}

const STEPS: StepDefinition[] = [
  {
    title: "Basic Information",
    description: "Who is this assessment for?",
    fields: ["age", "sex"],
    render: ({ values, errors, setValue }) => (
      <>
        <NumberField
          name="age"
          label="Age"
          unit="years"
          value={values.age ?? ""}
          onChange={(v) => setValue("age", v)}
          error={errors.age}
          min={25}
          max={100}
        />
        <RadioField
          name="sex"
          label="Sex"
          value={values.sex ?? ""}
          onChange={(v) => setValue("sex", v)}
          options={SEX_OPTIONS}
          error={errors.sex}
        />
      </>
    ),
  },
  {
    title: "Symptoms & Clinical Observations",
    description: "Chest pain and exercise responses.",
    fields: ["cp", "exang"],
    render: ({ values, errors, setValue }) => (
      <>
        <RadioField
          name="cp"
          label="Chest pain type"
          value={values.cp ?? ""}
          onChange={(v) => setValue("cp", v)}
          options={CHEST_PAIN_OPTIONS}
          error={errors.cp}
          hint="How chest discomfort has presented, if at all."
        />
        <RadioField
          name="exang"
          label="Exercise-induced angina"
          value={values.exang ?? ""}
          onChange={(v) => setValue("exang", v)}
          options={YES_NO_OPTIONS}
          error={errors.exang}
          hint="Chest pain brought on by physical exertion."
        />
      </>
    ),
  },
  {
    title: "Measurements & Diagnostic Indicators",
    description: "Routine measurements from a check-up or stress test.",
    fields: ["trestbps", "chol", "thalach", "oldpeak", "fbs", "restecg", "slope", "ca", "thal"],
    render: ({ values, errors, setValue }) => (
      <>
        <div className="grid gap-5 sm:grid-cols-2">
          <NumberField
            name="trestbps"
            label="Resting blood pressure"
            unit="mmHg"
            value={values.trestbps ?? ""}
            onChange={(v) => setValue("trestbps", v)}
            error={errors.trestbps}
            min={80}
            max={220}
          />
          <NumberField
            name="chol"
            label="Cholesterol"
            unit="mg/dl"
            value={values.chol ?? ""}
            onChange={(v) => setValue("chol", v)}
            error={errors.chol}
            min={100}
            max={600}
          />
          <NumberField
            name="thalach"
            label="Maximum heart rate achieved"
            unit="bpm"
            value={values.thalach ?? ""}
            onChange={(v) => setValue("thalach", v)}
            error={errors.thalach}
            min={60}
            max={220}
          />
          <NumberField
            name="oldpeak"
            label="ST depression"
            unit="mm"
            step="0.1"
            value={values.oldpeak ?? ""}
            onChange={(v) => setValue("oldpeak", v)}
            error={errors.oldpeak}
            hint="Measured during exercise relative to rest."
            min={0}
            max={10}
          />
        </div>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <RadioField
            name="fbs"
            label="Fasting blood sugar above 120 mg/dl"
            value={values.fbs ?? ""}
            onChange={(v) => setValue("fbs", v)}
            options={YES_NO_OPTIONS}
            error={errors.fbs}
          />
          <RadioField
            name="restecg"
            label="Resting ECG result"
            value={values.restecg ?? ""}
            onChange={(v) => setValue("restecg", v)}
            options={REST_ECG_OPTIONS}
            error={errors.restecg}
          />
          <RadioField
            name="slope"
            label="ST segment slope (peak exercise)"
            value={values.slope ?? ""}
            onChange={(v) => setValue("slope", v)}
            options={SLOPE_OPTIONS}
            error={errors.slope}
          />
          <RadioField
            name="ca"
            label="Major vessels affected"
            value={values.ca ?? ""}
            onChange={(v) => setValue("ca", v)}
            options={VESSEL_OPTIONS}
            error={errors.ca}
          />
          <RadioField
            name="thal"
            label="Thallium stress test result"
            value={values.thal ?? ""}
            onChange={(v) => setValue("thal", v)}
            options={THAL_OPTIONS}
            error={errors.thal}
          />
        </div>
      </>
    ),
  },
];

const TOTAL_STEPS = STEPS.length;

export function AssessmentForm() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const step = STEPS[stepIndex];
  const progress = useMemo(
    () => Math.round(((stepIndex + 1) / TOTAL_STEPS) * 100),
    [stepIndex]
  );

  const setValue = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => {
      const fieldKey = name as keyof FieldErrors;
      if (!prev[fieldKey]) return prev;
      const next = { ...prev };
      delete next[fieldKey];
      return next;
    });
  };

  const validateStep = (index: number): boolean => {
    const stepFields: readonly string[] = STEPS[index].fields;
    const result = validateAssessment(values);
    if (result.ok) {
      setErrors({});
      return true;
    }
    const stepErrors: FieldErrors = {};
    for (const field of stepFields) {
      const key = field as keyof FieldErrors;
      const message: string | undefined = result.errors[key];
      if (message) stepErrors[key] = message;
    }
    setErrors((prev) => ({ ...prev, ...stepErrors }));
    return Object.keys(stepErrors).length === 0;
  };

  const goNext = () => {
    if (!validateStep(stepIndex)) return;
    setStepIndex((i) => Math.min(i + 1, TOTAL_STEPS - 1));
  };

  const goBack = () => setStepIndex((i) => Math.max(i - 1, 0));

  const handleSubmit = async () => {
    // Full validation across all steps before submission.
    const result = validateAssessment(values);
    if (!result.ok) {
      setErrors(result.errors);
      const firstErrorStep = STEPS.findIndex((s) =>
        s.fields.some((f) => {
          const key = f as keyof FieldErrors;
          return Boolean(result.errors[key]);
        })
      );
      if (firstErrorStep >= 0) setStepIndex(firstErrorStep);
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const created = await api.createAssessment(result.data);
      toast.success("Assessment created");
      router.push(`/results/${created.id}`);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.";
      setSubmitError(message);
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  const fieldProps: FieldProps = { values, errors, setValue };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardDescription>
            Step {stepIndex + 1} of {TOTAL_STEPS}
          </CardDescription>
          <span className="text-xs text-muted-foreground" aria-hidden="true">
            {"█".repeat(progress / 10)}
            {"░".repeat(10 - progress / 10)}
          </span>
        </div>
        <Progress value={progress} className="mt-1 h-1.5" aria-hidden="true" />
        <CardTitle className="mt-3 text-xl">{step.title}</CardTitle>
        <CardDescription>{step.description}</CardDescription>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (stepIndex < TOTAL_STEPS - 1) goNext();
            else void handleSubmit();
          }}
          noValidate
        >
          <fieldset disabled={submitting} className="space-y-5">
            <legend className="sr-only">{step.title}</legend>
            <div
              className={cn(
                "grid gap-5",
                step.fields.length > 2 && "sm:grid-cols-1"
              )}
            >
              {step.render(fieldProps)}
            </div>

            {submitError && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{submitError}</span>
              </div>
            )}

            <div className="flex items-center justify-between gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={goBack}
                disabled={stepIndex === 0 || submitting}
              >
                <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" /> Back
              </Button>

              {stepIndex < TOTAL_STEPS - 1 ? (
                <Button type="submit">
                  Continue <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
                </Button>
              ) : (
                <Button type="submit" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  )}
                  {submitting ? "Analyzing assessment…" : "Analyze Assessment"}
                </Button>
              )}
            </div>
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
