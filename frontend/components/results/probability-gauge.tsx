"use client";

import { cn, formatPercentPrecise } from "@/lib/utils";
import { probabilityLevel } from "@/components/ui/probability-status";

interface ProbabilityGaugeProps {
  probability: number;
  size?: number;
  className?: string;
}

const LEVEL_COLOR: Record<string, string> = {
  low: "stroke-emerald-500",
  moderate: "stroke-amber-500",
  high: "stroke-rose-500",
};

const LEVEL_TEXT: Record<string, string> = {
  low: "text-emerald-700 dark:text-emerald-400",
  moderate: "text-amber-700 dark:text-amber-400",
  high: "text-rose-700 dark:text-rose-400",
};

export function ProbabilityGauge({
  probability,
  size = 176,
  className,
}: ProbabilityGaugeProps) {
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(probability, 0), 1);
  const offset = circumference * (1 - clamped);
  const level = probabilityLevel(clamped);

  return (
    <div
      role="img"
      aria-label={`Model-estimated disease probability ${formatPercentPrecise(clamped)}`}
      className={cn("relative inline-flex items-center justify-center", className)}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-muted"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            "--gauge-circumference": `${circumference}`,
            "--gauge-offset": `${offset}`,
          } as React.CSSProperties}
          className={cn("gauge-arc", LEVEL_COLOR[level])}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className={cn(
            "text-3xl font-semibold tabular-nums",
            LEVEL_TEXT[level]
          )}
        >
          {formatPercentPrecise(probability)}
        </span>
        <span className="text-xs text-muted-foreground">disease probability</span>
      </div>
    </div>
  );
}
