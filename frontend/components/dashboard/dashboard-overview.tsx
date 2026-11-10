"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  ChevronRight,
  Cpu,
  FileUp,
  Inbox,
  PlusCircle,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { ProbabilityBadge } from "@/components/ui/probability-status";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";
import { cn, formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type {
  AssessmentListResponse,
  HealthResponse,
  ReadinessResponse,
} from "@/types/api";

const RECENT_LIMIT = 5;

type Slice<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  errorStatus: number | null;
};

const idle = <T,>(): Slice<T> => ({ data: null, loading: true, error: null, errorStatus: null });

function sliceError(err: unknown): { message: string; status: number | null } {
  if (err instanceof ApiError) return { message: err.message, status: err.status };
  return { message: "Something went wrong. Please try again.", status: null };
}

function ServiceRow({ label, value }: { label: string; value: string }) {
  const ok = value.toLowerCase() === "ok" || value.toLowerCase() === "ready";
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="flex items-center gap-2 text-muted-foreground">
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            ok ? "bg-emerald-500" : "bg-amber-500"
          )}
          aria-hidden="true"
        />
        {label}
      </span>
      <span className="font-medium capitalize">{value}</span>
    </div>
  );
}

function StatCell({
  label,
  value,
  sub,
  valueClassName,
  loading,
}: {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  valueClassName?: string;
  loading: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm shadow-black/2 backdrop-blur-sm">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground/80">{label}</p>
      {loading ? (
        <Skeleton className="mt-2.5 h-6 w-16" />
      ) : (
        <p className={cn("mt-2 truncate text-xl font-semibold tabular-nums text-foreground", valueClassName)}>
          {value ?? "—"}
        </p>
      )}
      {sub && !loading && <p className="mt-1 truncate text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function DashboardOverview() {
  const { status: authStatus } = useAuth();
  const [health, setHealth] = useState<Slice<HealthResponse>>(idle);
  const [ready, setReady] = useState<Slice<ReadinessResponse>>(idle);
  const [recent, setRecent] = useState<Slice<AssessmentListResponse>>(idle);

  const loadHealth = useCallback(async () => {
    try {
      const data = await api.getHealth();
      setHealth({ data, loading: false, error: null, errorStatus: null });
    } catch (err) {
      const { message, status } = sliceError(err);
      setHealth({ data: null, loading: false, error: message, errorStatus: status });
    }
  }, []);

  const loadReady = useCallback(async () => {
    try {
      const data = await api.getReadiness();
      setReady({ data, loading: false, error: null, errorStatus: null });
    } catch (err) {
      const { message, status } = sliceError(err);
      setReady({ data: null, loading: false, error: message, errorStatus: status });
    }
  }, []);

  const loadRecent = useCallback(async () => {
    try {
      const data = await api.listAssessments(RECENT_LIMIT, 0);
      setRecent({ data, loading: false, error: null, errorStatus: null });
    } catch (err) {
      const { message, status } = sliceError(err);
      setRecent({ data: null, loading: false, error: message, errorStatus: status });
    }
  }, []);

  const retryRecent = () => {
    setRecent(idle());
    void loadRecent();
  };

  const retryHealth = () => {
    setHealth(idle());
    void loadHealth();
  };

  const retryReady = () => {
    setReady(idle());
    void loadReady();
  };

  useEffect(() => {
    void (async () => {
      await Promise.all([loadHealth(), loadReady(), loadRecent()]);
    })();
  }, [loadHealth, loadReady, loadRecent]);

  const signedOut = recent.errorStatus === 401 || authStatus === "anonymous";
  const recentItems = recent.data?.items ?? [];
  const totalCount = recent.data?.total;
  const latest = recentItems[0] ?? null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 md:py-10">
      <section className="relative overflow-hidden rounded-[28px] border border-border/80 bg-gradient-to-br from-primary/10 via-card to-card p-6 shadow-[0_20px_60px_-30px_rgba(15,23,42,0.45)] md:p-8">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.08),_transparent_35%)]" aria-hidden="true" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/8 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-primary">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              AI health intelligence
            </p>
            <h1 className="mt-4 text-balance text-3xl font-semibold tracking-tight md:text-4xl">
              Cardiovascular risk monitoring, designed for clarity.
            </h1>
            <p className="mt-3 max-w-xl text-pretty text-muted-foreground md:text-base">
              See how a calibrated machine-learning model interprets the health information you provide —
              with feature-level explanations, transparent uncertainty, and practical guidance.
            </p>
          </div>

          <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
            <Button asChild size="lg" className="rounded-full shadow-md shadow-primary/10">
              <Link href="/assessment">
                <PlusCircle className="size-4" aria-hidden="true" />
                New Assessment
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full border-border/80 bg-background/70">
              <Link href="/report">
                <FileUp className="size-4" aria-hidden="true" />
                Upload Report
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Key figures">
        <StatCell label="Total assessments" value={totalCount} loading={recent.loading} />
        <StatCell
          label="Recent assessment"
          value={latest ? formatPercentPrecise(latest.disease_probability) : null}
          sub={latest ? formatDateTime(latest.created_at) : undefined}
          loading={recent.loading}
        />
        <StatCell
          label="Model version"
          value={health.data ? `v${health.data.model_version}` : null}
          loading={health.loading}
        />
        <StatCell
          label="System status"
          value={
            ready.loading
              ? null
              : ready.data
                ? ready.data.status === "ready"
                  ? "Operational"
                  : "Degraded"
                : "Unknown"
          }
          valueClassName={
            ready.data?.status === "ready"
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-amber-600 dark:text-amber-400"
          }
          loading={ready.loading}
        />
      </section>

      <div
        className="mt-4 flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200"
        role="note"
      >
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          This tool does not diagnose, treat, or replace professional medical evaluation. For real health decisions,
          consult a qualified healthcare professional.
        </p>
      </div>

      <section className="mt-6 grid gap-4 lg:grid-cols-3" aria-label="Activity and system state">
        <Card className="lg:col-span-2 border-border/70 bg-card/80 shadow-sm">
          <CardHeader className="flex-row items-center justify-between border-b border-border/70 pb-4">
            <div>
              <CardTitle>Recent assessments</CardTitle>
              <CardDescription>
                {typeof totalCount === "number"
                  ? `${totalCount} stored in this environment`
                  : "Your latest model assessments"}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-muted-foreground sm:inline">
                Updated {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              <Button asChild variant="ghost" size="sm" className="rounded-full">
                <Link href="/history">
                  View all
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {recent.loading ? (
              <div className="space-y-3 py-2" aria-busy="true">
                <span className="sr-only" role="status">Loading recent assessments…</span>
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : recent.errorStatus === 401 || signedOut ? (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <Inbox className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                <div>
                  <p className="font-medium">Sign in to see your assessments</p>
                  <p className="text-sm text-muted-foreground">Assessments are private to each account.</p>
                </div>
                <Button asChild size="sm" className="rounded-full">
                  <Link href="/login">Sign in</Link>
                </Button>
              </div>
            ) : recent.error ? (
              <div className="flex flex-col items-start gap-3 py-6">
                <p role="alert" className="flex items-start gap-2 text-sm text-muted-foreground">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
                  {recent.error}
                </p>
                <Button variant="outline" size="sm" onClick={retryRecent} className="rounded-full">
                  <RefreshCw className="size-4" aria-hidden="true" /> Retry
                </Button>
              </div>
            ) : recentItems.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <Inbox className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                <div>
                  <p className="font-medium">No assessments yet</p>
                  <p className="text-sm text-muted-foreground">Complete your first assessment to see it here.</p>
                </div>
                <Button asChild size="sm" className="rounded-full">
                  <Link href="/assessment">Start Assessment</Link>
                </Button>
              </div>
            ) : (
              <ul className="-mx-2 divide-y divide-border/70">
                {recentItems.map((item) => (
                  <li key={item.id}>
                    <Link
                      href={`/results/${item.id}`}
                      className="group flex items-center justify-between gap-3 rounded-xl px-2 py-2.5 transition-colors hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="w-16 shrink-0 text-right font-semibold tabular-nums">
                          {formatPercentPrecise(item.disease_probability)}
                        </span>
                        <ProbabilityBadge
                          probability={item.disease_probability}
                          predictedDisease={item.predicted_disease}
                        />
                        <span className="hidden truncate text-xs text-muted-foreground sm:inline">
                          {formatDateTime(item.created_at)} · v{item.model_version}
                        </span>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="border-border/70 bg-card/80 shadow-sm">
            <CardHeader className="border-b border-border/70 pb-4">
              <CardDescription className="flex items-center gap-1.5">
                <Cpu className="h-3.5 w-3.5" aria-hidden="true" /> Model
              </CardDescription>
              <CardTitle className="text-lg">
                {health.loading ? (
                  <Skeleton className="h-6 w-24" />
                ) : health.data ? (
                  `v${health.data.model_version}`
                ) : (
                  "Unavailable"
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm">
              {health.error ? (
                <div className="flex flex-col items-start gap-2">
                  <p role="alert" className="text-muted-foreground">{health.error}</p>
                  <Button variant="outline" size="sm" onClick={retryHealth} className="rounded-full">
                    <RefreshCw className="size-4" aria-hidden="true" /> Retry
                  </Button>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Prediction engine</span>
                    <span className="font-medium">Calibrated ML</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Environment</span>
                    <span className="font-medium capitalize">{health.data?.app_env ?? "—"}</span>
                  </div>
                  <p className="text-xs leading-5 text-muted-foreground">
                    Logistic regression with probability calibration, evaluated on a locked test set.
                    Per-prediction feature contributions are shown with each result.
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 shadow-sm">
            <CardHeader className="border-b border-border/70 pb-4">
              <CardDescription className="flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5" aria-hidden="true" /> System status
              </CardDescription>
              <CardTitle className="text-lg">
                {ready.loading ? (
                  <Skeleton className="h-6 w-28" />
                ) : ready.data ? (
                  ready.data.status === "ready" ? (
                    <span className="text-emerald-600 dark:text-emerald-400">Operational</span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400">Degraded</span>
                  )
                ) : (
                  "Unknown"
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {ready.error ? (
                <div className="flex flex-col items-start gap-2">
                  <p role="alert" className="text-muted-foreground">{ready.error}</p>
                  <Button variant="outline" size="sm" onClick={retryReady} className="rounded-full">
                    <RefreshCw className="size-4" aria-hidden="true" /> Retry
                  </Button>
                </div>
              ) : ready.data ? (
                <div className="space-y-2.5">
                  <ServiceRow label="Database" value={ready.data.services.database} />
                  <ServiceRow label="Redis" value={ready.data.services.redis} />
                  <ServiceRow label="Model" value={ready.data.services.model} />
                  <ServiceRow label="Storage" value={ready.data.services.storage} />
                </div>
              ) : (
                <div className="space-y-2.5" aria-busy="true">
                  {[0, 1, 2].map((i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mt-4 grid gap-4 sm:grid-cols-2" aria-label="Get started">
        <Card className="border-border/70 bg-card/80 shadow-sm transition-colors hover:bg-accent/30 motion-reduce:transition-none">
          <CardContent className="flex items-start gap-4 pt-5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <PlusCircle className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <CardTitle className="text-base">Start a new assessment</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Enter the 13 inputs the model was trained on — most come from a routine check-up.
              </p>
              <Button asChild variant="link" size="sm" className="mt-1 px-0">
                <Link href="/assessment">
                  Open the form <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/70 bg-card/80 shadow-sm transition-colors hover:bg-accent/30 motion-reduce:transition-none">
          <CardContent className="flex items-start gap-4 pt-5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <BarChart3 className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <CardTitle className="text-base">Upload a report instead</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Let AI extract the values from a PDF or photo — you review and confirm every field before any prediction.
              </p>
              <Button asChild variant="link" size="sm" className="mt-1 px-0">
                <Link href="/report">
                  Upload a report <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
