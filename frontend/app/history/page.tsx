"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ChevronLeft, ChevronRight, Inbox, PlusCircle } from "lucide-react";

import { HistoryCards } from "@/components/history/history-cards";
import { HistoryTable } from "@/components/history/history-table";
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
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  // Fetch current page. All state updates happen AFTER the await, so this is
  // safe from both event handlers and effects (react-hooks/set-state-in-effect).
  const fetchPage = useCallback(async (currentOffset: number) => {
    try {
      const result = await api.listAssessments(PAGE_SIZE, currentOffset);
      setData(result);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load assessment history."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.listAssessments(PAGE_SIZE, offset);
        if (!cancelled) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load assessment history."
          );
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [offset]);

  const goTo = (nextOffset: number) => {
    setLoading(true);
    setOffset(nextOffset);
  };

  const retry = () => {
    setLoading(true);
    void fetchPage(offset);
  };

  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Assessment History</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Stored assessments from this demo environment.
          </p>
        </div>
        <Button asChild>
          <Link href="/assessment">
            <PlusCircle className="mr-2 h-4 w-4" aria-hidden="true" /> New Assessment
          </Link>
        </Button>
      </div>

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
              <Button variant="outline" onClick={retry}>
                Retry
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
              className="mt-4 flex items-center justify-between"
            >
              <p className="text-sm text-muted-foreground" aria-live="polite">
                Page {page} of {totalPages} · {total} total
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => goTo(Math.max(0, offset - PAGE_SIZE))}
                >
                  <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" /> Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => goTo(offset + PAGE_SIZE)}
                >
                  Next <ChevronRight className="ml-1 h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </nav>
          </>
        ) : null}
      </div>
    </div>
  );
}
