import type { Metadata } from "next";

import { ReportUploader } from "@/components/report/report-uploader";
import { RequireAuth } from "@/lib/use-auth";

export const metadata: Metadata = {
  title: "Upload Report",
};

export default function ReportPage() {
  return (
    <RequireAuth>
      <div className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Upload Medical Report</h1>
        <p className="mt-1 text-muted-foreground">
          Upload a check-up report (PDF, JPEG, PNG, or WEBP — max 10 MB).
          AI extracts the 13 cardiovascular inputs; you review and confirm
          every value before any prediction runs.
        </p>
        <div className="mt-6">
          <ReportUploader />
        </div>
      </div>
    </RequireAuth>
  );
}
