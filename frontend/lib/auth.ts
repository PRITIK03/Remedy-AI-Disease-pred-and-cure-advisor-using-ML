/**
 * Auth helpers (Phase 6) — cookie-session based.
 *
 * Security rules implemented here:
 * - The session cookie is HttpOnly and managed ENTIRELY by the browser; it is
 *   never read, stored, or echoed by this code (no localStorage/sessionStorage).
 * - Every request sends `credentials: "include"` so the browser attaches the
 *   cookies; unsafe requests also echo the CSRF cookie in X-CSRF-Token.
 * - `no-store` everywhere: auth state must never hit a cache.
 */

import type { AuthResponse, UserPublic } from "@/types/api";
import { ApiError, api } from "@/lib/api";

const CSRF_COOKIE = "remedy_csrf";

function readCsrfCookie(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match?.split("=")[1];
}

async function ensureCsrf(): Promise<string | undefined> {
  const existing = readCsrfCookie();
  if (existing) return existing;
  // Mint one via the public endpoint (sets the JS-readable cookie).
  await fetch(`${api.baseUrl()}/api/v1/auth/csrf`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return readCsrfCookie();
}

async function authRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD") {
    const token = await ensureCsrf();
    if (token) headers["X-CSRF-Token"] = token;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${api.baseUrl()}${path}`, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      let message = `Request failed with status ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        if (typeof body.detail === "string") message = body.detail;
      } catch {
        /* keep default */
      }
      throw new ApiError(res.status, "auth_error", message);
    }
    return (await res.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "timeout", "The request timed out. Please try again.");
    }
    throw new ApiError(0, "network_error", "Cannot reach the server. Is the backend running?");
  } finally {
    clearTimeout(timer);
  }
}

export interface RegisterInput {
  email: string;
  displayName: string;
  password: string;
}

export const auth = {
  /** Register a new account. Password confirmation happens in the form only. */
  async register(input: RegisterInput): Promise<UserPublic> {
    ensureCsrf().catch(() => undefined); // warm up the CSRF cookie in parallel
    const body = {
      email: input.email.trim(),
      display_name: input.displayName.trim(),
      password: input.password,
    };
    const res = await authRequest<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body,
    });
    return res.user;
  },

  /** Sign in. Failure messages are generic by backend design (anti-enumeration). */
  async login(email: string, password: string): Promise<UserPublic> {
    await ensureCsrf().catch(() => undefined);
    const res = await authRequest<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email: email.trim(), password },
    });
    return res.user;
  },

  /** Invalidate the server-side session and clear cookies. */
  async logout(): Promise<void> {
    try {
      await authRequest<{ logged_out: boolean }>("/api/v1/auth/logout", {
        method: "POST",
      });
    } catch {
      // Even if the call fails (e.g. already-expired session), clear locally.
    }
  },

  /** Current user, or null when not signed in. */
  async getCurrentUser(): Promise<UserPublic | null> {
    try {
      return await authRequest<UserPublic>("/api/v1/auth/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
};
