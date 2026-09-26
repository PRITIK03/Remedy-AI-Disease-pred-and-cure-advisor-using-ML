"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { FileUp, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import type { MedicalReportResponse } from "@/types/api";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp";
const MAX_BYTES = 10 * 1024 * 1024;

export function ReportUploader() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("File exceeds the 10 MB limit.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const report: MedicalReportResponse = await api.uploadReport(file);
      toast.success("Report processed — review the extracted values.");
      router.push(`/report/${report.id}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Upload failed. Please try again.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Medical report file</CardTitle>
        <CardDescription>
          Supported: PDF, JPEG, PNG, WEBP. Text PDFs parse directly; scans
          are read with vision AI.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label
          htmlFor="report-file"
          className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border px-6 py-10 text-center transition-colors hover:bg-accent/40"
        >
          <FileUp className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <span className="text-sm font-medium">
            {file ? file.name : "Choose a file to upload"}
          </span>
          <span className="text-xs text-muted-foreground">
            {file
              ? `${(file.size / 1024).toFixed(1)} KB — select again to change`
              : "PDF or image up to 10 MB"}
          </span>
          <input
            id="report-file"
            type="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Button onClick={handleUpload} disabled={!file || busy} className="w-full">
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
          {busy ? "Processing…" : "Upload and extract"}
        </Button>
      </CardContent>
    </Card>
  );
}
