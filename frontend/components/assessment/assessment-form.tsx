"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertCircle, ArrowLeft, ArrowRight, Check, ClipboardCheck, Loader2 } from "lucide-react";

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
  prettyFeatureName,
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
  shortTitle: string;
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
    shortTitle: "Basics",
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
    shortTitle: "Symptoms",
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
    shortTitle: "Measurements",
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
        <div className="grid gap-5 sm:grid-cols-2">
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

const TOTAL_STEPS = STEPS.length; // data steps; a final review step follows
const REVIEW_STEP = STEPS.length;

/** Real request phases — no fake progress percentages. */
type SubmitPhase = "validating" | "analyzing" | "preparing" | null;

export function AssessmentForm() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitPhase, setSubmitPhase] = useState<SubmitPhase>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const step = STEPS[stepIndex];
  const progress = useMemo(
    () => Math.round(((stepIndex + 1) / TOTAL_STEPS) * 100),
    [stepIndex]
  );
  const submitting = submitPhase !== null;

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
    setStepIndex((i) => Math.min(i + 1, REVIEW_STEP));
  };

  const goBack = () => setStepIndex((i) => Math.max(i - 1, 0));

  /** Readable value for a field, or null when empty (for the review step). */
  const reviewValue = (name: string): string | null => {
    const raw = values[name] ?? "";
    if (raw === "") return null;
    if (name === "sex") return SEX_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "cp") return CHEST_PAIN_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "fbs" || name === "exang")
      return YES_NO_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "restecg") return REST_ECG_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "slope") return SLOPE_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "ca") return VESSEL_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    if (name === "thal") return THAL_OPTIONS.find((o) => String(o.value) === raw)?.label ?? raw;
    return raw;
  };

  const handleSubmit = async () => {
    setSubmitPhase("validating");
    setSubmitError(null);
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
      setSubmitPhase(null);
      return;
    }
    try {
      setSubmitPhase("analyzing");
      const created = await api.createAssessment(result.data);
      setSubmitPhase("preparing");
      toast.success("Assessment created");
      router.push(`/results/${created.id}`);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.";
      setSubmitError(message);
      toast.error(message);
      setSubmitPhase(null);
    }
  };

  const fieldProps: FieldProps = { values, errors, setValue };

  const submitLabel =
    submitPhase === "validating"
      ? "Validating…"
      : submitPhase === "analyzing"
        ? "Analyzing…"
        : submitPhase === "preparing"
          ? "Preparing result…"
          : "Analyze Assessment";

  return (
    <Card>
      <CardHeader>
        {/* Step indicator */}
        <ol
          className="flex items-center gap-2"
          aria-label={`Step ${stepIndex + 1} of ${TOTAL_STEPS + 1}`}
        >
          {STEPS.map((s, i) => {
            const isDone = i < stepIndex;
            const isCurrent = i === stepIndex;
            return (
              <li key={s.shortTitle} className="flex min-w-0 items-center gap-2">
                <span
                  aria-current={isCurrent ? "step" : undefined}
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium transition-colors",
                    isDone && "border-primary bg-primary text-primary-foreground",
                    isCurrent && "border-primary text-primary",
                    !isDone && !isCurrent && "border-border text-muted-foreground"
                  )}
                >
                  {isDone ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={cn(
                    "hidden text-sm sm:inline",
                    isCurrent ? "font-medium text-foreground" : "text-muted-foreground"
                  )}
                >
                  {s.shortTitle}
                </span>
                {i < TOTAL_STEPS - 1 && (
                  <span
                    className={cn(
                      "h-px w-4 shrink-0 sm:w-6",
                      isDone ? "bg-primary" : "bg-border"
                    )}
                    aria-hidden="true"
                  />
                )}
              </li>
            );
          })}
          {/* Review chip terminates the indicator */}
          <li className="flex min-w-0 items-center gap-2">
            <span
              aria-current={stepIndex === REVIEW_STEP ? "step" : undefined}
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium transition-colors",
                stepIndex === REVIEW_STEP
                  ? "border-primary text-primary"
                  : "border-border text-muted-foreground"
              )}
            >
              <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
            <span
              className={cn(
                "hidden text-sm sm:inline",
                stepIndex === REVIEW_STEP
                  ? "font-medium text-foreground"
                  : "text-muted-foreground"
              )}
            >
              Review
            </span>
          </li>
        </ol>
        <Progress
          value={stepIndex === REVIEW_STEP ? 100 : progress}
          className="mt-4 h-1.5"
          aria-hidden="true"
        />
        <CardTitle className="mt-3 text-xl">
          {stepIndex === REVIEW_STEP ? "Review & Analyze" : step.title}
        </CardTitle>
        <CardDescription>
          {stepIndex === REVIEW_STEP
            ? "All values below are ready to send to the model."
            : step.description}
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (stepIndex < REVIEW_STEP) goNext();
            else void handleSubmit();
          }}
          noValidate
        >
          <fieldset disabled={submitting} className="space-y-5">
            <legend className="sr-only">{step.title}</legend>
            {stepIndex === REVIEW_STEP ? (
              /* Review step: readable summary of the entered values. */
              <div aria-busy={submitting} className="animate-page-enter">
                <p className="mb-4 text-sm text-muted-foreground">
                  Check everything before running the model — use Back to edit
                  any value.
                </p>
                <dl className="grid gap-x-6 gap-y-2 rounded-lg border border-border bg-muted/30 p-4 sm:grid-cols-2">
                  {STEPS.flatMap((s) => s.fields).map((field) => {
                    const label = prettyFeatureName(`numeric__${field}`)
                      .replace(/ \(male\)$/, "")
                      .replace("High fasting blood sugar", "Fasting blood sugar > 120 mg/dl")
                      .replace("Exercise-induced angina", "Exercise-induced angina")
                      .replace("Maximum heart rate", "Maximum heart rate achieved");
                    const value = reviewValue(field);
                    return (
                      <div
                        key={field}
                        className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5 last:border-0 sm:border-0"
                      >
                        <dt className="text-sm text-muted-foreground">{label}</dt>
                        <dd
                          className={cn(
                            "text-sm font-medium tabular-nums",
                            value === null && "text-destructive"
                          )}
                        >
                          {value ?? "Missing"}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              </div>
            ) : (
              <div
                aria-busy={submitting}
                className={cn(
                  "grid gap-5 transition-opacity",
                  submitting && "pointer-events-none opacity-60"
                )}
              >
                {step.render(fieldProps)}
              </div>
            )}

            {submitError && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{submitError}</span>
              </div>
            )}

            <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
              <Button
                type="button"
                variant="ghost"
                onClick={goBack}
                disabled={stepIndex === 0 || submitting}
              >
                <ArrowLeft className="size-4" aria-hidden="true" /> Back
              </Button>

              {stepIndex < REVIEW_STEP ? (
                <Button type="submit">
                  {stepIndex === REVIEW_STEP - 1 ? "Review" : "Continue"}{" "}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              ) : (
                <Button type="submit" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  )}
                  {submitting ? submitLabel : "Analyze Assessment"}
                </Button>
              )}
            </div>
          </fieldset>
          {/* Screen-reader announcement of the current async phase. */}
          <p className="sr-only" role="status" aria-live="polite">
            {submitting ? submitLabel : ""}
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
