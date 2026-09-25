"use client";

import Link from "next/link";
import { formatDateTime, formatPercentPrecise } from "@/lib/utils";
import type { AssessmentResponse } from "@/types/api";

import { Badge } from "@/components/ui/badge";
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
    <div className="hidden overflow-hidden rounded-lg border border-border md:block">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Date</TableHead>
            <TableHead scope="col">Probability</TableHead>
            <TableHead scope="col">Classification</TableHead>
            <TableHead scope="col">Model</TableHead>
            <TableHead scope="col">
              <span className="sr-only">Open</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>{formatDateTime(item.created_at)}</TableCell>
              <TableCell className="tabular-nums">
                {formatPercentPrecise(item.disease_probability)}
              </TableCell>
              <TableCell>
                <Badge variant={item.predicted_disease ? "outline" : "secondary"}>
                  {item.predicted_disease ? "Higher probability" : "Lower probability"}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                v{item.model_version}
              </TableCell>
              <TableCell className="text-right">
                <Link
                  href={`/results/${item.id}`}
                  className="underline underline-offset-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  View<span className="sr-only"> assessment from {formatDateTime(item.created_at)}</span>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
