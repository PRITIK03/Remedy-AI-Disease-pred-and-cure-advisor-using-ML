"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { ProbabilityBadge } from "@/components/ui/probability-status";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type { AssessmentResponse } from "@/types/api";

export function HistoryCards({ items }: { items: AssessmentResponse[] }) {
  return (
    <div className="space-y-3 md:hidden">
      {items.map((item) => (
        <Card key={item.id} className="transition-colors hover:bg-accent/40 motion-reduce:transition-none">
          <CardContent className="p-0">
            <Link
              href={`/results/${item.id}`}
              className="flex items-center justify-between gap-3 p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <div className="min-w-0 space-y-1.5">
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-semibold tabular-nums">
                    {formatPercentPrecise(item.disease_probability)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    disease probability
                  </span>
                </div>
                <ProbabilityBadge
                  probability={item.disease_probability}
                  predictedDisease={item.predicted_disease}
                />
                <p className="truncate text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)} ·{" "}
                  {item.source === "report" ? "Report" : "Manual"} · v{item.model_version}
                </p>
              </div>
              <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
