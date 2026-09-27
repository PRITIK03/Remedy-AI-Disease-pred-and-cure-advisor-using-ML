"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { CircleAlert, FileScan, Loader2, Pencil, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { validateAssessment } from "@/lib/validation";
import type { AssessmentCreate, MedicalReportResponse } from "@/types/api";
import { REPORT_FIELDS } from "@/components/report/report-fields";

export function initialReportValues(report: MedicalReportResponse): Record<string, string> {
  const out: Record<string, string> = {};
  const feats = report.latest_extraction?.extracted_features ?? {};
  for (const f of REPORT_FIELDS) {
    const v = feats[f.key];
    out[f.key] = v === null || v === undefined ? "" : String(v);
  }
  return out;
}

/** Pure per-render derivation; recomputes exactly when `values` changes. */
function validateValues(values: Record<string, string>) {
  const numeric: Record<string, number> = {};
  for (const [k, v] of Object.entries(values)) {
    if (v === "") return { ok: false as const, errors: { [k]: "Required" } };
    const n = Number(v);
    if (Number.isNaN(n)) return { ok: false as const, errors: { [k]: "Must be a number" } };
    numeric[k] = n;
  }
  return validateAssessment(numeric);
}

/** Visual confidence indicator driven by the extraction's real confidences. */
function ConfidenceDot({ confidence }: { confidence: number }) {
  const level =
    confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full",
        level === "high" && "bg-emerald-500",
        level === "medium" && "bg-amber-500",
        level === "low" && "bg-rose-500"
      )}
      aria-hidden="true"
    />
  );
}

export function ReportReviewForm({ report }: { report: MedicalReportResponse }) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>(() =>
    initialReportValues(report)
  );
  const [busy, setBusy] = useState(false);
  const validation = validateValues(values);

  async function handleConfirm() {
    if (!validation.ok) {
      toast.error("Fix the highlighted fields before confirming.");
      return;
    }
    setBusy(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(values).map(([k, v]) => [k, Number(v)])
      ) as unknown as AssessmentCreate;
      const created = await api.confirmReport(report.id, payload);
      toast.success("Assessment created from report.");
      router.push(`/results/${created.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Confirmation failed.");
    } finally {
      setBusy(false);
    }
  }

  const extraction = report.latest_extraction;

  return (
    <div>
      {report.status === "failed" && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm"
        >
          <p className="flex items-start gap-2 text-destructive">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              Extraction failed: {report.error_message ?? "unknown error"}. Enter
              values manually below.
            </span>
          </p>
        </div>
      )}

      {extraction?.notes && (
        <p className="mt-4 flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
          <FileScan className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>AI notes: {extraction.notes}</span>
        </p>
      )}

      <div
        className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200"
        role="note"
      >
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          Verify every value against your report. Nothing is predicted until you
          confirm.
        </p>
      </div>

      {/* Flow explainer so the confirmation step is visually obvious. */}
      <ol className="mt-4 grid gap-2 rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground sm:grid-cols-4">
        <li className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs">1</span>
          AI extracted these values
        </li>
        <li className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs">2</span>
          You review them
        </li>
        <li className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">3</span>
          <span className="font-medium text-foreground">You confirm</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs">4</span>
          Assessment is created
        </li>
      </ol>

      <Card className="mt-4">
        <CardHeader className="border-b [.border-b]:pb-4">
          <CardTitle>Confirm values</CardTitle>
          <CardDescription>
            Edit any field, then confirm to run the ML prediction. Confidence
            reflects how certain the AI extraction was for each value.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 pt-6 sm:grid-cols-2">
          {REPORT_FIELDS.map((f) => {
            const conf = extraction?.confidences?.[f.key];
            const evidence = extraction?.evidence?.[f.key];
            const original = extraction?.extracted_features?.[f.key];
            const current = values[f.key] ?? "";
            const userEdited =
              current !== "" &&
              current !== (original === null || original === undefined ? "" : String(original));
            const fieldError = !validation.ok
              ? (validation.errors as Record<string, string>)[f.key]
              : undefined;
            return (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={`report-${f.key}`} className="justify-start gap-2">
                  {f.label}
                  {userEdited ? (
                    <span
                      className="ml-1 inline-flex items-center gap-1 text-xs font-normal text-foreground/70"
                      title="You edited this value — it overrides the AI extraction"
                    >
                      <Pencil className="h-3 w-3" aria-hidden="true" />
                      edited
                    </span>
                  ) : (
                    typeof conf === "number" && (
                      <span
                        className="ml-1 inline-flex items-center gap-1 text-xs font-normal text-muted-foreground"
                        title={`AI extraction confidence ${(conf * 100).toFixed(0)}%`}
                      >
                        <ConfidenceDot confidence={conf} />
                        confidence {(conf * 100).toFixed(0)}%
                      </span>
                    )
                  )}
                </Label>
                <Input
                  id={`report-${f.key}`}
                  inputMode="decimal"
                  placeholder={f.hint}
                  value={current}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.key]: e.target.value }))
                  }
                  aria-invalid={fieldError ? true : undefined}
                  className={cn("h-10", fieldError && "border-destructive")}
                />
                {fieldError && (
                  <p className="text-xs font-medium text-destructive" role="alert">
                    {fieldError}
                  </p>
                )}
                {evidence && !userEdited && (
                  <p className="truncate text-xs text-muted-foreground" title={evidence}>
                    Evidence: {evidence || "—"}
                  </p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Button
        onClick={handleConfirm}
        disabled={busy || !validation.ok}
        className="mt-6 w-full"
        size="lg"
      >
        {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
        {busy ? "Creating assessment…" : "Confirm and create assessment"}
      </Button>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Confirming creates an assessment from these values — you can edit them
        above before continuing.
      </p>
    </div>
  );
}
