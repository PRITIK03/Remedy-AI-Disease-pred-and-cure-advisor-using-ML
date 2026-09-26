"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Activity, ClipboardList, FileUp, Home, Moon, PlusCircle, Sun } from "lucide-react";

import { api, ApiError } from "@/lib/api";
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
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-foreground/80 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
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

  return (
    <div
      className="flex items-center gap-2 text-sm"
      role="status"
      aria-live="polite"
      aria-label={`Backend status: ${status}`}
    >
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 rounded-full",
          status === "ok" && "bg-emerald-500",
          status === "down" && "bg-red-400",
          status === "checking" && "bg-amber-400 animate-pulse"
        )}
        aria-hidden="true"
      />
      <span className="hidden text-muted-foreground sm:inline">
        {status === "ok" && "System operational"}
        {status === "down" && "Backend unavailable"}
        {status === "checking" && "Checking…"}
      </span>
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Activity className="h-5 w-5 text-primary" aria-hidden="true" />
          <span>Remedy-AI</span>
        </Link>

        <nav aria-label="Main navigation" className="ml-4 hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className={cn(
                "rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                pathname === item.href
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <StatusIndicator />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>

      {/* Mobile nav */}
      <nav
        aria-label="Main navigation"
        className="flex items-center justify-around border-t border-border px-2 py-1.5 md:hidden"
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-md px-3 py-1 text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                active ? "text-primary font-medium" : "text-muted-foreground"
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
