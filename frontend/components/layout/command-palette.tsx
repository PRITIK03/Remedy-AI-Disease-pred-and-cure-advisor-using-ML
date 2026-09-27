"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  ClipboardList,
  FileUp,
  Home,
  Moon,
  PlusCircle,
  Search,
  Sun,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  run: (ctx: { router: ReturnType<typeof useRouter>; toggleTheme: () => void }) => void;
}

/**
 * Lightweight command palette (Ctrl/Cmd + K, or the header Search button).
 * No extra dependency: a filtered list in a positioned overlay. Real routes only.
 */
export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const setOpen = onOpenChange;

  const toggleTheme = () =>
    setTheme(resolvedTheme === "dark" ? "light" : "dark");

  const commands: Command[] = useMemo(
    () => [
      {
        id: "assessment",
        label: "New assessment",
        hint: "Start the 3-step form",
        icon: PlusCircle,
        run: ({ router }) => router.push("/assessment"),
      },
      {
        id: "report",
        label: "Upload report",
        hint: "AI extracts the values",
        icon: FileUp,
        run: ({ router }) => router.push("/report"),
      },
      {
        id: "history",
        label: "View history",
        hint: "All stored assessments",
        icon: ClipboardList,
        run: ({ router }) => router.push("/history"),
      },
      {
        id: "dashboard",
        label: "Go to dashboard",
        hint: "Overview and system status",
        icon: Home,
        run: ({ router }) => router.push("/"),
      },
      {
        id: "theme",
        label: "Toggle theme",
        hint: "Light or dark",
        icon: resolvedTheme === "dark" ? Sun : Moon,
        run: ({ toggleTheme }) => toggleTheme(),
      },
    ],
    [resolvedTheme]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(q) || c.hint.toLowerCase().includes(q)
    );
  }, [commands, query]);

  // Global shortcut: Ctrl/Cmd + K toggles, Escape closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
        setQuery("");
        setActiveIndex(0);
      } else if (e.key === "Escape") {
        onOpenChange(false);
      }
    };
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // Reset the query each time it opens; rAF defers state updates out of the
  // synchronous effect pass (same pattern as the theme toggle).
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      setQuery("");
      setActiveIndex(0);
      inputRef.current?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [open]);

  if (!open) return null;

  const runCommand = (command: Command) => {
    setOpen(false);
    command.run({ router, toggleTheme });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close command palette"
        onClick={() => setOpen(false)}
        className="absolute inset-0 cursor-default bg-foreground/20 backdrop-blur-[2px]"
      />

      <div className="relative w-full max-w-md animate-page-enter overflow-hidden rounded-xl border border-border bg-popover shadow-lg shadow-black/5">
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && filtered[activeIndex]) {
                e.preventDefault();
                runCommand(filtered[activeIndex]);
              }
            }}
            placeholder="Type a command…"
            aria-label="Search commands"
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground sm:block">
            ESC
          </kbd>
        </div>

        <ul className="max-h-72 overflow-y-auto p-1.5" role="listbox">
          {filtered.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              No matching commands
            </li>
          ) : (
            filtered.map((command, i) => {
              const Icon = command.icon;
              return (
                <li key={command.id} role="option" aria-selected={i === activeIndex}>
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(i)}
                    onClick={() => runCommand(command)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                      i === activeIndex
                        ? "bg-accent text-accent-foreground"
                        : "text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{command.label}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {command.hint}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
