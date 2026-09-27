"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Activity, ClipboardList, FileUp, Home, Moon, PlusCircle, Search, Sun } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { CommandPalette } from "@/components/layout/command-palette";
import { UserMenu } from "@/components/layout/user-menu";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: Home },
  { href: "/assessment", label: "New Assessment", icon: PlusCircle },
  { href: "/report", label: "Upload Report", icon: FileUp },
  { href: "/history", label: "History", icon: ClipboardList },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // rAF defers the state update out of the synchronous effect pass,
    // avoiding cascading renders flagged by react-hooks/set-state-in-effect.
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <button
      type="button"
      aria-label="Toggle color theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-foreground/70 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {mounted && resolvedTheme === "dark" ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}

type BackendStatus = "checking" | "ok" | "down";

function StatusIndicator() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const ready = await api.getReadiness();
        if (!cancelled) setStatus(ready.status === "ready" ? "ok" : "down");
      } catch (error) {
        if (!cancelled) {
          setStatus("down");
          if (error instanceof ApiError && error.status === 0) return; // offline: stop polling fast
        }
      }
    };
    void check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const label =
    status === "ok" ? "System operational" : status === "down" ? "Backend unavailable" : "Checking…";

  return (
    <div
      className="flex items-center gap-2 text-sm"
      role="status"
      aria-live="polite"
      aria-label={`Backend status: ${status}`}
      title={label}
    >
      <span
        className={cn(
          "inline-block h-2 w-2 shrink-0 rounded-full",
          status === "ok" && "bg-emerald-500",
          status === "down" && "bg-red-400",
          status === "checking" && "animate-pulse bg-amber-400"
        )}
        aria-hidden="true"
      />
      <span className="hidden text-muted-foreground lg:inline">{label}</span>
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:gap-4">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Activity className="h-4 w-4" aria-hidden="true" />
          </span>
          <span>Remedy-AI</span>
        </Link>

        <nav aria-label="Main navigation" className="ml-2 hidden items-center gap-0.5 md:flex">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                className={cn(
                  "relative flex items-center gap-1.5 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  active
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {/* Icons-only between md and lg keeps the header within the
                    viewport at 768px; aria-label preserves the name. */}
                <span className="hidden lg:inline">{item.label}</span>
                {active && (
                  <span
                    className="absolute inset-x-2.5 -bottom-[9px] h-0.5 rounded-full bg-primary"
                    aria-hidden="true"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5">
          {/* Command palette trigger */}
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            className="hidden h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:inline-flex"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Search</span>
            <kbd className="rounded border border-border bg-muted px-1 text-[10px]">⌘K</kbd>
          </button>
          <StatusIndicator />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />

      {/* Mobile nav */}
      <nav
        aria-label="Main navigation"
        className="flex items-center justify-around border-t border-border px-2 py-1.5 md:hidden"
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-md px-3 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                active ? "font-medium text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label.replace("New ", "")}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
