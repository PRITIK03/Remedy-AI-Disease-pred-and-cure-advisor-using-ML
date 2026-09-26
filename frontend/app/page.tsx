import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Activity, BarChart3, BookOpenCheck, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Dashboard",
};

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      {/* Hero */}
      <section className="rounded-2xl border border-border bg-card px-6 py-12 text-center md:py-16">
        <Badge variant="outline" className="mb-4">
          Educational prototype
        </Badge>
        <h1 className="mx-auto max-w-2xl text-balance text-3xl font-semibold tracking-tight md:text-4xl">
          AI-Assisted Cardiovascular Health Assessment
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-muted-foreground md:text-lg">
          Understand how a machine-learning model interprets the health
          information you provide. Educational decision support — not a
          diagnosis.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button asChild size="lg" className="w-full sm:w-auto">
            <Link href="/assessment">
              Start Assessment
              <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary" className="w-full sm:w-auto">
            <Link href="/report">Upload Report</Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
            <Link href="/history">View History</Link>
          </Button>
        </div>
      </section>

      {/* Honest-scope notice */}
      <div
        className="mx-auto mt-6 flex max-w-3xl items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200"
        role="note"
      >
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          This tool does not diagnose, treat, or replace professional medical
          evaluation. For real health decisions, consult a qualified
          healthcare professional.
        </p>
      </div>

      {/* Info cards */}
      <section className="mt-10 grid gap-4 sm:grid-cols-3" aria-label="System overview">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" /> Model
            </CardDescription>
            <CardTitle className="text-2xl">v2.0.0</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Versioned pipeline with corrected target semantics.
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> Prediction
              Engine
            </CardDescription>
            <CardTitle className="text-2xl">Calibrated ML</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Logistic regression with probability calibration, evaluated on a
            locked test set.
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <BookOpenCheck className="h-3.5 w-3.5" aria-hidden="true" />{" "}
              Evidence / Explainability
            </CardDescription>
            <CardTitle className="text-2xl">Feature Contributions</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Per-prediction model contributions available with each result;
            richer evidence arrives in later AI phases.
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
