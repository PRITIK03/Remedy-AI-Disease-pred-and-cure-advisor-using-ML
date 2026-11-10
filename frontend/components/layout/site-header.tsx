"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import {
  Activity,
  ClipboardList,
  FileUp,
  Home,
  Moon,
  PlusCircle,
  Search,
  Sparkles,
  Sun,
} from "lucide-react";

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
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <button
      type="button"
      aria-label="Toggle color theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border/80 bg-background/70 text-foreground/70 transition-all duration-200 hover:border-primary/30 hover:bg-primary/5 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
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
          if (error instanceof ApiError && error.status === 0) return;
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
      className="flex items-center gap-2 rounded-full border border-border/80 bg-card/80 px-2.5 py-1.5 shadow-sm"
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
      <span className="hidden text-xs text-muted-foreground lg:inline">{label}</span>
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-background/85 backdrop-blur-xl supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:gap-4">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-full border border-transparent px-1.5 py-1 font-semibold tracking-tight text-foreground transition-colors hover:border-primary/20 hover:bg-primary/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-cyan-500 text-primary-foreground shadow-sm shadow-primary/20">
            <Activity className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="flex items-center gap-1.5 text-sm sm:text-base">
            Remedy-AI
            <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          </span>
        </Link>

        <nav aria-label="Main navigation" className="ml-2 hidden items-center gap-1 md:flex">
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
                  "relative flex items-center gap-2 rounded-full px-3 py-2 text-sm transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  active
                    ? "bg-primary/8 text-foreground shadow-sm ring-1 ring-primary/15"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="hidden lg:inline">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            className="hidden h-9 items-center gap-2 rounded-full border border-border/80 bg-card/80 px-3 text-sm text-muted-foreground transition-all duration-200 hover:shadow-sm hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring lg:flex"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Search</span>
            <kbd className="rounded-md border border-border bg-muted px-1 text-[10px] text-muted-foreground">⌘K</kbd>
          </button>
          <StatusIndicator />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />

      <nav
        aria-label="Main navigation"
        className="flex items-center justify-around border-t border-border/80 bg-background/70 px-2 py-1.5 md:hidden"
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
                "flex flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 text-[11px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
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
