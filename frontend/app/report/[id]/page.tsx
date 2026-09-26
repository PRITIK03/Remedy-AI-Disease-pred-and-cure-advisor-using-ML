"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ReportReviewForm } from "@/components/report/report-review-form";
import { RequireAuth } from "@/lib/use-auth";
import { api, ApiError } from "@/lib/api";
import type { MedicalReportResponse } from "@/types/api";

function ReviewInner({ id }: { id: string }) {
  const [report, setReport] = useState<MedicalReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const fetched = await api.getReport(id);
        if (!cancelled) setReport(fetched);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Load failed.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);
  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 text-center text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" aria-hidden="true" />
        <p className="mt-2 text-sm">Loading report…</p>
      </div>
    );
  }
  if (error || !report) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <p role="alert" className="text-sm text-destructive">{error ?? "Report not found."}</p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/report"><ArrowLeft className="mr-2 h-4 w-4" />Back to upload</Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/report"><ArrowLeft className="mr-2 h-4 w-4" />Back to upload</Link>
      </Button>
      <h1 className="text-2xl font-semibold tracking-tight">Review extracted values</h1>
      <p className="mt-1 text-muted-foreground">{report.filename} · status: {report.status}</p>
      <div className="mt-4">
        <ReportReviewForm report={report} />
      </div>
    </div>
  );
}

export default function ReportReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <ReviewInner id={id} />
    </RequireAuth>
  );
}

