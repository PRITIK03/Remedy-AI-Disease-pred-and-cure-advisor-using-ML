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
import { Badge } from "@/components/ui/badge";
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

import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type { AssessmentResponse, ExplanationResponse } from "@/types/api";

export default function ResultsPage({
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

  const load = useCallback(async () => {
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
  }, [id]);

  const loadExplanation = useCallback(async () => {
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
    setExplLoading(true);
    void loadExplanation();
  };

  const retry = () => {
    setLoading(true);
    void load();
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

  useEffect(() => {
    if (!explOpen || explanation) return;
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
  }, [explOpen, explanation, id]);

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
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" /> Retry
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

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Model Assessment</h1>
          <p className="text-sm text-muted-foreground">
            {formatDateTime(assessment.created_at)}
          </p>
        </div>
        <Badge variant={highProbability ? "outline" : "secondary"} className="text-sm">
          {highProbability
            ? "Higher model-estimated probability of disease"
            : "Lower model-estimated probability of disease"}
        </Badge>
      </div>

      {/* Main result */}
      <Card className="mt-6">
        <CardContent className="flex flex-col items-center gap-6 py-8 sm:flex-row sm:justify-around">
          <ProbabilityGauge probability={assessment.disease_probability} />
          <div className="space-y-1 text-center sm:text-left">
            <p className="text-sm text-muted-foreground">
              Model-estimated disease probability
            </p>
            <p className="text-4xl font-semibold tabular-nums">
              {formatPercentPrecise(assessment.disease_probability)}
            </p>
            <p className="text-xs text-muted-foreground">
              probability_label: {assessment.probability_label}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Model information */}
      <Card className="mt-4">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Model Information</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-muted-foreground">Model version</p>
            <p className="font-medium">{assessment.model_version}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Selected model</p>
            <p className="font-medium capitalize">
              {assessment.selected_model.replace(/_/g, " ")}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* AI guidance — lazy, explicit user opt-in (no LLM call on render) */}
      <AiGuidance assessmentId={assessment.id} modelProbability={assessment.disease_probability} />

      {/* Feature contributions */}
      <Collapsible open={explOpen} onOpenChange={setExplOpen} className="mt-4">
        <Card>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="flex w-full items-center justify-between px-6 py-4"
              aria-expanded={explOpen}
            >
              <span className="font-semibold">What influenced this model output?</span>
              <ChevronDown
                className={`h-4 w-4 transition-transform ${explOpen ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="pt-0">
              <p className="mb-4 text-xs text-muted-foreground">
                Model feature contributions — how much each input pushed the
                model&apos;s estimate up (amber) or down (green). These are
                model contributions, <strong>not causes of disease</strong>.
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

      {/* About this prediction */}
      <Collapsible className="mt-4">
        <Card>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="flex w-full items-center justify-between px-6 py-4"
            >
              <span className="font-semibold">About this prediction</span>
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
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

      <div className="mt-6 flex gap-3">
        <Button asChild variant="outline">
          <Link href="/assessment">
            <ClipboardList className="mr-2 h-4 w-4" aria-hidden="true" /> New Assessment
          </Link>
        </Button>
        <Button asChild variant="ghost">
          <Link href="/history">View History</Link>
        </Button>
      </div>
    </div>
  );
}
