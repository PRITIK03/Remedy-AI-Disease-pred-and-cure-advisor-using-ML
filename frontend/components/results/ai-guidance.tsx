"use client";

import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  BookOpenCheck,
  ChevronDown,
  ExternalLink,
  Info,
  ListChecks,
  Sparkles,
  Stethoscope,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { api, ApiError } from "@/lib/api";
import type { GuidanceResponse } from "@/types/api";

type GuidanceState =
  | { phase: "idle" }
  | { phase: "loading"; startedAt: number }
  | { phase: "ready"; data: GuidanceResponse }
  | { phase: "review"; message: string }
  | { phase: "error"; message: string; retriable: boolean };

interface ReviewDetailShape {
  message?: string;
  review_required?: boolean;
  workflow_status?: string;
}

interface AiGuidanceProps {
  assessmentId: string;
  /** Passed through so the guidance text can reflect the model result. */
  modelProbability: number;
}

/**
 * Lazy-loaded, opt-in AI guidance. No LLM call happens until the user
 * clicks "View AI Guidance" (cost + performance rule from the phase plan).
 *
 * Wording discipline: this is "AI-generated guidance grounded in retrieved
 * sources" — never "cure", "treatment plan" or "diagnosis".
 */
export function AiGuidance({ assessmentId }: AiGuidanceProps) {
  const [state, setState] = useState<GuidanceState>({ phase: "idle" });
  const [open, setOpen] = useState(false);

  const load = async () => {
    setState({ phase: "loading", startedAt: Date.now() });
    try {
      const data = await api.getGuidance(assessmentId);
      setState({ phase: "ready", data });
    } catch (err) {
      if (err instanceof ApiError) {
        // 202: the workflow flagged this case for human review — the
        // guidance exists but is deliberately NOT released to the client.
        if (err.status === 202) {
          const detail = (
            err as ApiError & { detail?: ReviewDetailShape }
          ).detail;
          setState({
            phase: "review",
            message:
              detail?.message ??
              "This assessment has been flagged for additional review.",
          });
          return;
        }
        const retriable = err.status === 502 || err.status === 0;
        setState({
          phase: "error",
          message:
            err.status === 503
              ? "AI guidance is not configured on this server. Ask the operator to set LLM_API_KEY / LLM_MODEL and ingest knowledge sources."
              : err.status === 404
                ? "This assessment no longer exists."
                : err.message,
          retriable,
        });
      } else {
        setState({
          phase: "error",
          message: "Guidance is unavailable right now.",
          retriable: true,
        });
      }
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen && state.phase === "idle") {
      void load();
    }
  };

  const retry = () => {
    if (state.phase === "error" && state.retriable) void load();
  };

  // Explicit, honest status label shown in the section header.
  const STATUS_LABEL: Record<GuidanceState["phase"], { text: string; className: string } | null> = {
    idle: null,
    loading: {
      text: "Loading",
      className: "border-border bg-muted/50 text-muted-foreground",
    },
    ready: {
      text: "Available",
      className:
        "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300",
    },
    review: {
      text: "Review required",
      className:
        "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
    },
    error: {
      text: "Unavailable",
      className:
        "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300",
    },
  };
  const statusBadge = STATUS_LABEL[state.phase];

  return (
    <Collapsible open={open} onOpenChange={handleOpenChange} className="mt-4">
      <Card>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            className="flex w-full items-center justify-between gap-2 px-6 py-4"
            aria-expanded={open}
          >
            <span className="flex items-center gap-2 font-semibold">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Guidance
              </span>
              AI Health Guidance
              {statusBadge && (
                <span
                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${statusBadge.className}`}
                >
                  {statusBadge.text}
                </span>
              )}
            </span>
            <ChevronDown
              className={`h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="pt-0">
            <p className="mb-4 flex items-start gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              AI-generated guidance grounded in retrieved sources. This is
              general health information — <strong>not a diagnosis</strong>,
              not medical advice, and never a replacement for professional
              evaluation.
            </p>

            {state.phase === "loading" && <GuidanceLoading />}

            {state.phase === "review" && <ReviewPending message={state.message} />}

            {state.phase === "error" && (
              <div className="space-y-2 text-sm">
                <p role="alert" className="text-muted-foreground">{state.message}</p>
                {state.retriable && (
                  <Button variant="outline" size="sm" onClick={retry}>
                    Retry
                  </Button>
                )}
              </div>
            )}

            {state.phase === "ready" && <GuidanceBody data={state.data} />}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function ReviewPending({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
    >
      <p className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
          aria-hidden="true"
        />
        <span>{message}</span>
      </p>
      <p className="mt-2 pl-6 text-xs text-muted-foreground">
        Guidance for flagged cases is held until the review is completed. The
        model output above remains valid and unchanged.
      </p>
    </div>
  );
}

function GuidanceLoading() {
  return (
    <div className="space-y-3" aria-busy="true">
      <p className="text-sm text-muted-foreground" role="status">
        Loading evidence… generating guidance…
      </p>
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-5 w-full" />
      <Skeleton className="h-5 w-5/6" />
      <Skeleton className="h-5 w-2/3" />
    </div>
  );
}

function GuidanceBody({ data }: { data: GuidanceResponse }) {
  const g = data.guidance;
  return (
    <div className="space-y-6">
      {/* Summary */}
      <section aria-labelledby="guidance-summary">
        <h3
          id="guidance-summary"
          className="mb-1 flex items-center gap-2 text-sm font-semibold"
        >
          <BookOpenCheck className="h-4 w-4" aria-hidden="true" /> Summary
        </h3>
        <p className="text-sm text-muted-foreground">{g.summary}</p>
      </section>

      {/* What influenced the model */}
      <section aria-labelledby="guidance-factors">
        <h3
          id="guidance-factors"
          className="mb-1 flex items-center gap-2 text-sm font-semibold"
        >
          <Activity className="h-4 w-4" aria-hidden="true" /> What influenced
          the model
        </h3>
        <p className="text-sm text-muted-foreground">{g.model_explanation}</p>
        {g.key_factors.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {g.key_factors.map((f) => (
              <li key={f}>
                <Badge variant="secondary" className="text-xs">
                  {f}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Separator />

      {/* General guidance */}
      {g.guidance.length > 0 && (
        <section aria-labelledby="guidance-general">
          <h3
            id="guidance-general"
            className="mb-1 flex items-center gap-2 text-sm font-semibold"
          >
            <ListChecks className="h-4 w-4" aria-hidden="true" /> General
            guidance
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {g.guidance.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {/* When to seek care */}
      {g.when_to_seek_care.length > 0 && (
        <section aria-labelledby="guidance-care">
          <h3
            id="guidance-care"
            className="mb-1 flex items-center gap-2 text-sm font-semibold"
          >
            <Stethoscope className="h-4 w-4" aria-hidden="true" /> When to
            seek professional care
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {g.when_to_seek_care.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Limitations */}
      <section aria-labelledby="guidance-limits" className="rounded-md border bg-muted/40 p-3">
        <h3
          id="guidance-limits"
          className="mb-1 flex items-center gap-2 text-sm font-semibold"
        >
          <AlertTriangle className="h-4 w-4" aria-hidden="true" /> Limitations
        </h3>
        <p className="text-sm text-muted-foreground">{g.limitations}</p>
      </section>

      {/* Sources — only backend-verified citations, clickable */}
      {g.citations.length > 0 && (
        <section aria-labelledby="guidance-sources">
          <h3
            id="guidance-sources"
            className="mb-2 text-sm font-semibold"
          >
            Sources
          </h3>
          <ul className="space-y-2">
            {g.citations.map((c, i) => (
              <li key={`${c.url}-${i}`} className="text-sm">
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium underline underline-offset-2 hover:text-foreground"
                >
                  {c.title}
                  <ExternalLink
                    className="ml-1 inline h-3.5 w-3.5"
                    aria-hidden="true"
                  />
                </a>
                <span className="text-muted-foreground">
                  {" "}
                  — {c.source}, section: {c.section}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs text-muted-foreground">
        Grounded in {g.evidence_count} retrieved evidence excerpt
        {g.evidence_count === 1 ? "" : "s"} · prompt version{" "}
        {data.prompt_version} · model output shown above is authoritative and
        was not altered by the AI.
      </p>
    </div>
  );
}
