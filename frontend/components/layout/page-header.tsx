import type { ReactNode } from "react";

import { Breadcrumbs, type Crumb } from "@/components/layout/breadcrumbs";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  /** Breadcrumb trail shown above the title. */
  crumbs?: Crumb[];
  className?: string;
}

/**
 * Consistent page header: tight, aligned, same vertical rhythm on every page.
 * Content below always starts after the same gap, so pages feel like one
 * product instead of separate demos.
 */
export function PageHeader({
  title,
  description,
  actions,
  crumbs,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {crumbs && crumbs.length > 0 && (
          <Breadcrumbs items={crumbs} className="mb-3" />
        )}
        <h1 className="text-balance text-2xl font-semibold tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-pretty text-sm text-muted-foreground md:text-base">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
