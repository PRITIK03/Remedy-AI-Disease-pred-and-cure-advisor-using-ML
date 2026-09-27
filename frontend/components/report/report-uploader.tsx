"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, FileText, FileUp, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";
import type { MedicalReportResponse } from "@/types/api";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp";
const MAX_BYTES = 10 * 1024 * 1024;

type UploadPhase = "idle" | "processing";

export function ReportUploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const busy = phase !== "idle";

  function validateAndSet(nextFile: File | null) {
    if (!nextFile) return;
    setError(null);
    if (nextFile.size > MAX_BYTES) {
      setError("File exceeds the 10 MB limit.");
      return;
    }
    setFile(nextFile);
  }

  async function handleUpload() {
    if (!file) return;
    setPhase("processing");
    setError(null);
    try {
      // The API call covers upload + server-side extraction in one request;
      // the UI shows a single honest processing state (no fake progress).
      const report: MedicalReportResponse = await api.uploadReport(file);
      toast.success("Report processed — review the extracted values.");
      router.push(`/report/${report.id}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Upload failed. Please try again.";
      setError(message);
      toast.error(message);
      setPhase("idle");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Medical report file</CardTitle>
        <CardDescription>
          Supported: PDF, JPEG, PNG, WEBP. Text PDFs parse directly; scans are
          read with vision AI.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {file ? (
          <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                setFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              disabled={busy}
              aria-label="Remove selected file"
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        ) : (
          <label
            htmlFor="report-file"
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const dropped = e.dataTransfer.files?.[0];
              if (dropped) validateAndSet(dropped);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-6 py-12 text-center transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring hover:bg-accent/40",
              dragOver && "border-primary bg-primary/5"
            )}
          >
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-muted">
              <FileUp className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            </span>
            <span className="text-sm font-medium">
              Choose a file or drag it here
            </span>
            <span className="text-xs text-muted-foreground">
              PDF or image up to 10 MB
            </span>
            <input
              ref={inputRef}
              id="report-file"
              type="file"
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => validateAndSet(e.target.files?.[0] ?? null)}
            />
          </label>
        )}

        {error && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        <Button
          onClick={handleUpload}
          disabled={!file || busy}
          className="w-full"
          size="lg"
        >
          {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          {phase === "processing" ? "Processing…" : "Upload and extract"}
        </Button>

        {/* Flow explanation so the user knows what happens next. */}
        <ol className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 pt-2 text-xs text-muted-foreground">
          <li>1. Upload</li>
          <li aria-hidden="true">·</li>
          <li>2. AI extracts values</li>
          <li aria-hidden="true">·</li>
          <li>3. You review &amp; confirm</li>
          <li aria-hidden="true">·</li>
          <li>4. Assessment created</li>
        </ol>
      </CardContent>
    </Card>
  );
}
