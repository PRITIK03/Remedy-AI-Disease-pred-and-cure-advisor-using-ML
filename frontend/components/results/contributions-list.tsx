"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { prettyFeatureName } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { FeatureContribution } from "@/types/api";

interface ContributionsListProps {
  contributions: FeatureContribution[] | null;
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function ContributionsList({
  contributions,
  loading,
  error,
  onRetry,
}: ContributionsListProps) {
  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading feature contributions">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm">
        <p className="text-muted-foreground">{error}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 underline underline-offset-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  if (!contributions || contributions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Feature contributions are not available for this assessment.
      </p>
    );
  }

  const maxAbs = Math.max(...contributions.map((c) => Math.abs(c.shap_value)), 1e-9);

  return (
    <ul className="space-y-3">
      {contributions.map((c) => {
        const widthPct = (Math.abs(c.shap_value) / maxAbs) * 100;
        const pushesUp = c.shap_value > 0;
        return (
          <li key={c.feature} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span>{prettyFeatureName(c.feature)}</span>
              <span
                className={cn(
                  "tabular-nums text-xs",
                  pushesUp ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"
                )}
              >
                {pushesUp ? "+" : ""}
                {c.shap_value.toFixed(3)}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  pushesUp ? "bg-amber-500/80" : "bg-emerald-500/80"
                )}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
