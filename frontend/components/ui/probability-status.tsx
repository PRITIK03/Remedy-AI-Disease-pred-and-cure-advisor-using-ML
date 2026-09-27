import { cn } from "@/lib/utils";

export type ProbabilityLevel = "low" | "moderate" | "high";

/** Shared probability bands used by the gauge, history rows and dashboard. */
export function probabilityLevel(p: number): ProbabilityLevel {
  if (p >= 0.5) return "high";
  if (p >= 0.2) return "moderate";
  return "low";
}

const LEVEL_STYLES: Record<
  ProbabilityLevel,
  { badge: string; dot: string; label: string }
> = {
  low: {
    badge:
      "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300",
    dot: "bg-emerald-500",
    label: "Lower probability",
  },
  moderate: {
    badge:
      "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
    dot: "bg-amber-500",
    label: "Moderate probability",
  },
  high: {
    badge:
      "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300",
    dot: "bg-rose-500",
    label: "Higher probability",
  },
};

/**
 * Consistent classification badge across pages. Reflects the model's
 * probability band only — wording stays honest (no "diagnosis").
 */
export function ProbabilityBadge({
  probability,
  predictedDisease,
  className,
}: {
  probability: number;
  predictedDisease: boolean;
  className?: string;
}) {
  const level = probabilityLevel(probability);
  const style = LEVEL_STYLES[level];
  const label = predictedDisease ? style.label : "Lower probability";
  return (
    <span
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        style.badge,
        className
      )}
    >
      <span className={cn("inline-block h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden="true" />
      {label}
    </span>
  );
}
