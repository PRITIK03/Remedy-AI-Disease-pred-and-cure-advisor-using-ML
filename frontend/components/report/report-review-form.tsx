"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
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

export function ReportReviewForm({ report }: { report: MedicalReportResponse }) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>(() => initialReportValues(report));
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
        <div role="alert" className="mt-4 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          Extraction failed: {report.error_message ?? "unknown error"}. Enter values manually below.
        </div>
      )}
      {extraction?.notes && (
        <p className="mt-4 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
          AI notes: {extraction.notes}
        </p>
      )}
      <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="note">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>Verify every value against your report. Nothing is predicted until you confirm.</p>
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Confirm values</CardTitle>
          <CardDescription>Edit any field, then confirm to run the ML prediction.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {REPORT_FIELDS.map((f) => {
            const conf = extraction?.confidences?.[f.key];
            const evidence = extraction?.evidence?.[f.key];
            const fieldError = !validation.ok
              ? (validation.errors as Record<string, string>)[f.key]
              : undefined;
            return (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={`report-${f.key}`}>
                  {f.label}
                  {typeof conf === "number" && (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      confidence {(conf * 100).toFixed(0)}%
                    </span>
                  )}
                </Label>
                <Input
                  id={`report-${f.key}`}
                  inputMode="decimal"
                  placeholder={f.hint}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  aria-invalid={fieldError ? true : undefined}
                />
                {fieldError && <p className="text-xs text-destructive">{fieldError}</p>}
                {evidence && <p className="text-xs text-muted-foreground">Evidence: {evidence || "—"}</p>}
              </div>
            );
          })}
        </CardContent>
      </Card>
      <Button onClick={handleConfirm} disabled={busy || !validation.ok} className="mt-6 w-full" size="lg">
        {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
        {busy ? "Creating assessment…" : "Confirm and create assessment"}
      </Button>
    </div>
  );
}

