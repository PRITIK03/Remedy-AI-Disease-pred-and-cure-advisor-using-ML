"use client";

/**
 * Minimal authenticated-state mechanism (Phase 6).
 *
 * - `useAuth` fetches /auth/me once per mount tree and exposes login/logout.
 * - `<RequireAuth>` guards protected routes: unauthenticated visitors are
 *   redirected to /login. This is UX only — the backend remains the real
 *   protection (server-side authorization on every API call).
 */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { auth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import type { UserPublic } from "@/types/api";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: AuthStatus;
  user: UserPublic | null;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<UserPublic>;
  register: (input: {
    email: string;
    displayName: string;
    password: string;
  }) => Promise<UserPublic>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserPublic | null>(null);

  const refresh = useCallback(async () => {
    try {
      const current = await auth.getCurrentUser();
      setUser(current);
      setStatus(current ? "authenticated" : "anonymous");
    } catch {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const u = await auth.login(email, password);
      setUser(u);
      setStatus("authenticated");
      return u;
    },
    []
  );

  const register = useCallback(
    async (input: { email: string; displayName: string; password: string }) => {
      const u = await auth.register(input);
      setUser(u);
      setStatus("authenticated");
      return u;
    },
    []
  );

  const logout = useCallback(async () => {
    await auth.logout();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo(
    () => ({ status, user, refresh, login, register, logout }),
    [status, user, refresh, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status !== "authenticated") {
    // Loading (brief) or redirecting — render nothing to avoid flashing data.
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-sm text-muted-foreground" role="status">
          Checking your session…
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

/** Map ApiError to a user-safe message (generic for auth failures). */
export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Invalid email or password.";
    if (error.status === 429) return "Too many attempts. Please wait and try again.";
    if (error.status === 403) return "Session expired. Please sign in again.";
    if (error.status === 0) return error.message;
    return error.message;
  }
  return "Something went wrong. Please try again.";
}
