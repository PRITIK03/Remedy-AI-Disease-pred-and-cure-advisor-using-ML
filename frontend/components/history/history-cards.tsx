"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type { AssessmentResponse } from "@/types/api";

export function HistoryCards({ items }: { items: AssessmentResponse[] }) {
  return (
    <div className="space-y-3 md:hidden">
      {items.map((item) => (
        <Card key={item.id} className="transition-colors hover:bg-accent/40">
          <CardContent className="p-0">
            <Link
              href={`/results/${item.id}`}
              className="flex items-center justify-between gap-3 p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <div className="space-y-1">
                <p className="font-medium tabular-nums">
                  {formatPercentPrecise(item.disease_probability)}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    disease probability
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)} · v{item.model_version}
                </p>
                <Badge variant={item.predicted_disease ? "outline" : "secondary"} className="text-xs">
                  {item.predicted_disease ? "Higher probability" : "Lower probability"}
                </Badge>
              </div>
              <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
