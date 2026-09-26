import type { Metadata } from "next";
import { Info } from "lucide-react";

import { AssessmentForm } from "@/components/assessment/assessment-form";
import { RequireAuth } from "@/lib/use-auth";

export const metadata: Metadata = {
  title: "New Assessment",
};

export default function AssessmentPage() {
  return (
    <RequireAuth>
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">New Assessment</h1>
        <p className="mt-1 text-muted-foreground">
          Provide the 13 inputs the model was trained on. You can find them on a
          routine check-up report.
        </p>

        <div
          role="note"
          className="mt-4 flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground"
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            This demo environment stores assessments so you can revisit them in
            History. Do not enter information you would not be comfortable
            storing. This is not a medical diagnosis.
          </p>
        </div>

        <div className="mt-6">
          <AssessmentForm />
        </div>
      </div>
    </RequireAuth>
  );
}
