"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { ProbabilityBadge } from "@/components/ui/probability-status";
import { formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type { AssessmentResponse } from "@/types/api";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function HistoryTable({ items }: { items: AssessmentResponse[] }) {
  return (
    <div className="hidden overflow-hidden rounded-xl border border-border md:block">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50 hover:bg-muted/50">
            <TableHead scope="col">Date</TableHead>
            <TableHead scope="col" className="text-right">Probability</TableHead>
            <TableHead scope="col">Classification</TableHead>
            <TableHead scope="col">Source</TableHead>
            <TableHead scope="col">Model</TableHead>
            <TableHead scope="col">
              <span className="sr-only">Open</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id} className="group">
              <TableCell className="whitespace-nowrap">
                {formatDateTime(item.created_at)}
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                {formatPercentPrecise(item.disease_probability)}
              </TableCell>
              <TableCell>
                <ProbabilityBadge
                  probability={item.disease_probability}
                  predictedDisease={item.predicted_disease}
                />
              </TableCell>
              <TableCell className="text-muted-foreground">
                {item.source === "report" ? "Report" : "Manual"}
              </TableCell>
              <TableCell className="text-muted-foreground">
                v{item.model_version}
              </TableCell>
              <TableCell className="text-right">
                <Link
                  href={`/results/${item.id}`}
                  className="inline-flex items-center gap-1 rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  View
                  <ChevronRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
                    aria-hidden="true"
                  />
                  <span className="sr-only">
                    assessment from {formatDateTime(item.created_at)}
                  </span>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
