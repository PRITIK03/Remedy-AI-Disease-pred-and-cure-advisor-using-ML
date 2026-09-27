"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Loader2,
  PlusCircle,
  RefreshCw,
} from "lucide-react";

import { HistoryCards } from "@/components/history/history-cards";
import { HistoryTable } from "@/components/history/history-table";
import { PageHeader } from "@/components/layout/page-header";
import { RequireAuth } from "@/lib/use-auth";
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
import { cn } from "@/lib/utils";
import type { AssessmentListResponse } from "@/types/api";

const PAGE_SIZE = 10;

export default function HistoryPage() {
  return (
    <RequireAuth>
      <HistoryContent />
    </RequireAuth>
  );
}

function HistoryContent() {
  const [data, setData] = useState<AssessmentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  // Single fetch path: runs on mount and whenever `offset` changes
  // (pagination). All state updates happen AFTER the await.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.listAssessments(PAGE_SIZE, offset);
        if (!cancelled) {
          setData(result);
          setError(null);
          setLoading(false);
          setRefreshing(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load assessment history."
          );
          setLoading(false);
          setRefreshing(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [offset]);

  // Pagination just moves the offset; the effect refetches the new page.
  const goTo = (nextOffset: number) => {
    if (nextOffset === offset) return;
    setLoading(true);
    setOffset(nextOffset);
  };

  // Manual refresh re-runs the same fetch for the page currently shown,
  // including the error-retry case. All state updates happen after await.
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    if (refreshTick === 0) return; // mount is handled by the offset effect
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.listAssessments(PAGE_SIZE, offset);
        if (!cancelled) {
          setData(result);
          setError(null);
          setRefreshing(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load assessment history."
          );
          setRefreshing(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshTick, offset]);

  const refresh = () => {
    setRefreshing(true);
    setRefreshTick((t) => t + 1);
  };

  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 animate-page-enter md:py-10">
      <PageHeader
        title="Assessment History"
        description="Stored assessments from this demo environment."
        actions={
          <>
            <Button
              variant="outline"
              size="icon"
              onClick={refresh}
              disabled={refreshing}
              aria-label="Refresh history"
            >
              <Loader2
                className={cn("size-4", refreshing ? "animate-spin" : "hidden")}
                aria-hidden="true"
              />
              <RefreshCw
                className={cn("size-4", refreshing && "hidden")}
                aria-hidden="true"
              />
            </Button>
            <Button asChild>
              <Link href="/assessment">
                <PlusCircle className="size-4" aria-hidden="true" /> New Assessment
              </Link>
            </Button>
          </>
        }
      />

      <div aria-live="polite" aria-busy={loading} className="mt-6">
        {loading ? (
          <div className="space-y-3">
            <span className="sr-only">Loading assessment history…</span>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : error ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-5 w-5" aria-hidden="true" />
                Could not load history
              </CardTitle>
              <CardDescription>{error}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={refresh} disabled={refreshing}>
                <RefreshCw className="size-4" aria-hidden="true" /> Retry
              </Button>
            </CardContent>
          </Card>
        ) : total === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <Inbox className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
              <div>
                <p className="font-medium">No assessments yet</p>
                <p className="text-sm text-muted-foreground">
                  Complete your first assessment to see it here.
                </p>
              </div>
              <Button asChild>
                <Link href="/assessment">Start Assessment</Link>
              </Button>
            </CardContent>
          </Card>
        ) : data ? (
          <>
            <HistoryTable items={data.items} />
            <HistoryCards items={data.items} />

            {/* Pagination */}
            <nav
              aria-label="History pagination"
              className="mt-4 flex flex-wrap items-center justify-between gap-3"
            >
              <p className="text-sm text-muted-foreground" aria-live="polite">
                {rangeStart}–{rangeEnd} of {total} · Page {page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0 || loading}
                  onClick={() => goTo(Math.max(0, offset - PAGE_SIZE))}
                >
                  <ChevronLeft className="size-4" aria-hidden="true" /> Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= total || loading}
                  onClick={() => goTo(offset + PAGE_SIZE)}
                >
                  Next <ChevronRight className="size-4" aria-hidden="true" />
                </Button>
              </div>
            </nav>
          </>
        ) : null}
      </div>
    </div>
  );
}
