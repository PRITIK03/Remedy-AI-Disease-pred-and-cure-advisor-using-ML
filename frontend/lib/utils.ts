import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a probability as a percentage string, e.g. 0.3483 -> "35%". */
export function formatPercent(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** Format a probability with one decimal, e.g. 0.3483 -> "34.8%". */
export function formatPercentPrecise(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

/** ISO timestamp -> locale string (safe for SSR hydration when client-only). */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
