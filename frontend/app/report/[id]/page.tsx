"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { PageHeader } from "@/components/layout/page-header";
import { ReportReviewForm } from "@/components/report/report-review-form";
import { RequireAuth } from "@/lib/use-auth";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
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
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 px-4 py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
        <p className="text-sm" role="status">Loading report…</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" aria-hidden="true" />
              Could not load report
            </CardTitle>
            <CardDescription>{error ?? "Report not found."}</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-3">
            <Button variant="outline" onClick={() => window.location.reload()}>
              <RefreshCw className="size-4" aria-hidden="true" /> Retry
            </Button>
            <Button asChild variant="ghost">
              <Link href="/report">Back to upload</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 animate-page-enter md:py-10">
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/" },
          { label: "Upload Report", href: "/report" },
          { label: "Review extracted values" },
        ]}
        className="mb-4"
      />

      <PageHeader
        title="Review extracted values"
        description={`${report.filename} · uploaded ${formatDateTime(report.created_at)}`}
      />

      <div className="mt-6">
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
