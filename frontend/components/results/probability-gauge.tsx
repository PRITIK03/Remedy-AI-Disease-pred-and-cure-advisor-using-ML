"use client";

import { cn } from "@/lib/utils";
import { formatPercentPrecise } from "@/lib/utils";

interface ProbabilityGaugeProps {
  probability: number;
  size?: number;
  className?: string;
}

export function ProbabilityGauge({
  probability,
  size = 180,
  className,
}: ProbabilityGaugeProps) {
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(probability, 0), 1);
  const offset = circumference * (1 - clamped);

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
          className={cn(
            "transition-[stroke-dashoffset] duration-700 motion-reduce:transition-none",
            probability >= 0.5 ? "stroke-amber-500" : "stroke-emerald-500"
          )}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold tabular-nums">
          {formatPercentPrecise(probability)}
        </span>
        <span className="text-xs text-muted-foreground">disease probability</span>
      </div>
    </div>
  );
}
