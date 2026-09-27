"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ChevronDown,
  ClipboardList,
  Info,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { AiGuidance } from "@/components/results/ai-guidance";
import { ContributionsList } from "@/components/results/contributions-list";
import { ProbabilityGauge } from "@/components/results/probability-gauge";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";

import { api, ApiError, apiBaseUrl } from "@/lib/api";
import { RequireAuth } from "@/lib/use-auth";
import { cn, formatDateTime } from "@/lib/utils";
import type { AssessmentResponse, ExplanationResponse } from "@/types/api";

export default function ResultsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <RequireAuth>
      <ResultsContent params={params} />
    </RequireAuth>
  );
}

function ResultsContent({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [explLoading, setExplLoading] = useState(true);
  const [explError, setExplError] = useState<string | null>(null);
  const [explOpen, setExplOpen] = useState(false);

  const loadExplanation = useCallback(async () => {
    setExplLoading(true);
    try {
      const data = await api.getExplanation(id);
      setExplanation(data);
      setExplError(null);
    } catch (err) {
      setExplError(
        err instanceof ApiError
          ? err.message
          : "Feature contributions are unavailable right now."
      );
    } finally {
      setExplLoading(false);
    }
  }, [id]);

  const retryExplanation = () => {
    void loadExplanation();
  };

  const retry = () => {
    setLoading(true);
    void (async () => {
      try {
        const data = await api.getAssessment(id);
        setAssessment(data);
        setError(null);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Failed to load the assessment."
        );
      } finally {
        setLoading(false);
      }
    })();
  };

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.getAssessment(id);
        if (!cancelled) {
          setAssessment(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load the assessment."
          );
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Lazy-load contributions the first time the section is opened.
  useEffect(() => {
    if (!explOpen || explanation || explError) return;
    let cancelled = false;
    void (async () => {
      setExplLoading(true);
      try {
        const data = await api.getExplanation(id);
        if (!cancelled) {
          setExplanation(data);
          setExplError(null);
          setExplLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setExplError(
            err instanceof ApiError
              ? err.message
              : "Feature contributions are unavailable right now."
          );
          setExplLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [explOpen, explanation, explError, id]);

  if (loading) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 px-4 py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
        <p role="status">Loading assessment…</p>
      </div>
    );
  }

  if (error || !assessment) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" aria-hidden="true" />
              Could not load assessment
            </CardTitle>
            <CardDescription>{error ?? "Assessment not found."}</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-3">
            <Button onClick={retry} variant="outline">
              <RefreshCw className="size-4" aria-hidden="true" /> Retry
            </Button>
            <Button asChild variant="ghost">
              <Link href="/history">Go to History</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const highProbability = assessment.predicted_disease;
  const sourceLabel =
    assessment.source === "report" ? "From uploaded report" : "Manual entry";

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 animate-page-enter md:py-10">
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/" },
          { label: "History", href: "/history" },
          { label: `Assessment ${assessment.id.slice(0, 8)}` },
        ]}
        className="mb-4"
      />

      {/* Header + clean metadata row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">
            Assessment Result
          </h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-muted-foreground">
            <span>{formatDateTime(assessment.created_at)}</span>
            <span aria-hidden="true" className="opacity-50">·</span>
            <span>{sourceLabel}</span>
            <span aria-hidden="true" className="opacity-50">·</span>
            <span>model v{assessment.model_version}</span>
          </p>
        </div>
      </div>

      {/* Main result — the gauge is the single visual anchor */}
      <Card className="mt-6">
        <CardContent className="flex flex-col items-center gap-6 py-8 sm:flex-row sm:justify-center sm:gap-12 sm:py-10">
          <ProbabilityGauge probability={assessment.disease_probability} />
          <div className="max-w-xs space-y-2 text-center sm:text-left">
            <p className="text-sm font-medium">Model-estimated disease probability</p>
            <p
              className={cn(
                "text-sm text-pretty",
                highProbability
                  ? "text-rose-700 dark:text-rose-400"
                  : "text-emerald-700 dark:text-emerald-400"
              )}
            >
              {highProbability
                ? "The model estimates a higher probability of disease."
                : "The model estimates a lower probability of disease."}
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              A probability, not a yes/no answer. This estimate is not a
              diagnosis — see the notes below for context and limitations.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Feature contributions */}
      <Collapsible open={explOpen} onOpenChange={setExplOpen} className="mt-4">
        <Card>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="flex w-full items-center justify-between gap-2 px-6 py-4"
              aria-expanded={explOpen}
            >
              <span className="flex items-baseline gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Interpretation
                </span>
                <span className="font-semibold">What influenced the model?</span>
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none",
                  explOpen && "rotate-180"
                )}
                aria-hidden="true"
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="pt-0">
              <p className="mb-4 text-xs text-muted-foreground">
                Feature contributions — how much each input pushed the model&apos;s
                estimate up (amber) or down (green). These are model
                contributions, <strong>not causes of disease</strong>.
              </p>
              <ContributionsList
                contributions={explanation?.contributions ?? null}
                loading={explLoading}
                error={explError}
                onRetry={retryExplanation}
              />
              {explanation && (
                <p className="mt-4 text-xs text-muted-foreground">
                  Method: {explanation.method}
                </p>
              )}
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* AI guidance — lazy, explicit user opt-in (no LLM call on render) */}
      <AiGuidance assessmentId={assessment.id} modelProbability={assessment.disease_probability} />

      {/* About this prediction */}
      <Collapsible className="mt-4">
        <Card>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="flex w-full items-center justify-between gap-2 px-6 py-4"
            >
              <span className="font-semibold">About this prediction</span>
              <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-2 pt-0 text-sm text-muted-foreground">
              <p className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                The output is probabilistic: a model-estimated probability, not
                a yes/no medical answer.
              </p>
              <Separator />
              <p>
                The model was trained on a small historical dataset (303
                records). Its estimates carry real uncertainty.
              </p>
              <Separator />
              <p>
                This result is <strong>not a diagnosis</strong>. Real health
                decisions require a qualified healthcare professional.
              </p>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      <div className="mt-6 flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/assessment">
            <ClipboardList className="size-4" aria-hidden="true" /> New Assessment
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/history">View History</Link>
        </Button>
      </div>

      {/* Interoperability (Phase 8): read-only FHIR R4 export. */}
      <p className="mt-4 text-xs text-muted-foreground">
        Need this in a healthcare system?{" "}
        <a
          href={`${apiBaseUrl()}/api/v1/fhir/assessments/${encodeURIComponent(assessment.id)}`}
          className="underline underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          Export as FHIR R4
        </a>{" "}
        — a read-only Bundle of Patient, Observation, and DiagnosticReport
        resources generated from this assessment. It is not an EHR export and
        contains no diagnosis.
      </p>
    </div>
  );
}
