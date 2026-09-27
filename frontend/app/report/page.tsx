import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";
import { ReportUploader } from "@/components/report/report-uploader";
import { RequireAuth } from "@/lib/use-auth";

export const metadata: Metadata = {
  title: "Upload Report",
};

export default function ReportPage() {
  return (
    <RequireAuth>
      <div className="mx-auto max-w-3xl px-4 py-8 animate-page-enter md:py-10">
        <PageHeader
          title="Upload Medical Report"
          description="Upload a check-up report (PDF, JPEG, PNG, or WEBP — max 10 MB). AI extracts the 13 cardiovascular inputs; you review and confirm every value before any prediction runs."
        />
        <div className="mt-6">
          <ReportUploader />
        </div>
      </div>
    </RequireAuth>
  );
}
