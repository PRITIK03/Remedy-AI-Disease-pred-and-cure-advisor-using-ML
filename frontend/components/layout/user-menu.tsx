"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/use-auth";

export function UserMenu() {
  const { status, user, logout } = useAuth();
  const router = useRouter();

  if (status === "loading") {
    return <div className="h-9 w-24 animate-pulse rounded-md bg-muted" aria-hidden="true" />;
  }

  if (status === "anonymous") {
    return (
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link href="/login">Sign in</Link>
        </Button>
        {/* Register collapses to an icon button below lg to keep the header
            inside the viewport on narrow laptops (1024px). */}
        <Button asChild size="sm" className="hidden lg:inline-flex">
          <Link href="/register">Register</Link>
        </Button>
        <Button asChild size="icon-sm" className="lg:hidden" aria-label="Create an account">
          <Link href="/register">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span
        className="hidden max-w-[10rem] items-center gap-1.5 truncate rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground lg:inline-flex"
        title={user?.email}
      >
        <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="truncate">{user?.display_name ?? user?.email}</span>
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          void logout().then(() => router.replace("/"));
        }}
      >
        <LogOut className="mr-1.5 h-4 w-4" aria-hidden="true" />
        <span className="hidden lg:inline">Sign out</span>
      </Button>
    </div>
  );
}
