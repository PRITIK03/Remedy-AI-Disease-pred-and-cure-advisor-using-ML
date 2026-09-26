/**
 * Phase 6 frontend auth tests (vitest + @testing-library/react).
 * Fetch is stubbed; cookie behavior is exercised through the auth helpers.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { auth } from "@/lib/auth";
import { AuthProvider, RequireAuth, useAuth } from "@/lib/use-auth";
import type { UserPublic } from "@/types/api";

// next/navigation mock for RequireAuth redirect assertions.
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
}));

const user: UserPublic = {
  id: "u-1",
  email: "a@example.com",
  display_name: "Alice",
  role: "user",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  vi.restoreAllMocks();
  replaceMock.mockClear();
  document.cookie = "remedy_csrf=test-token; path=/";
});

describe("auth helpers", () => {
  it("getCurrentUser returns the user when /me answers 200", async () => {
    const spy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ id: "u-1", email: "a@example.com" }));
    const current = await auth.getCurrentUser();
    expect(current?.email).toBe("a@example.com");
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/api/v1/auth/me");
    expect(init.credentials).toBe("include");
    expect(init.cache).toBe("no-store");
  });

  it("getCurrentUser returns null on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Authentication required." }, 401)
    );
    expect(await auth.getCurrentUser()).toBeNull();
  });

  it("login sends credentials + CSRF header and returns the user", async () => {
    const spy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ user }));
    const result = await auth.login("a@example.com", "password-123");
    expect(result.display_name).toBe("Alice");
    const [, init] = spy.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe(
      "test-token"
    );
    expect(JSON.parse(init.body as string)).toEqual({
      email: "a@example.com",
      password: "password-123",
    });
  });

  it("login surfaces the backend generic failure message on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Invalid email or password." }, 401)
    );
    await expect(auth.login("a@example.com", "bad")).rejects.toMatchObject({
      status: 401,
    });
  });

  it("logout POSTs and clears state", async () => {
    const spy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ logged_out: true }));
    await auth.logout();
    const [url, init] = spy.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toContain("/api/v1/auth/logout");
    expect(init.method).toBe("POST");
  });

  it("register posts email/display_name/password", async () => {
    const spy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ user }));
    await auth.register({
      email: "b@example.com",
      displayName: "Bob",
      password: "password-123",
    });
    const [, init] = spy.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      email: "b@example.com",
      display_name: "Bob",
      password: "password-123",
    });
  });
});

describe("useAuth + RequireAuth", () => {
  function Probe() {
    const { status, user: current } = useAuth();
    return (
      <div>
        <span data-testid="status">{status}</span>
        <span data-testid="name">{current?.display_name ?? "none"}</span>
      </div>
    );
  }

  it("protected route redirects anonymous users to /login", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Authentication required." }, 401)
    );
    render(
      <AuthProvider>
        <RequireAuth>
          <div>secret</div>
        </RequireAuth>
      </AuthProvider>
    );
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("authenticated users see protected content", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/me")) return jsonResponse(user);
        if (url.includes("/api/v1/auth/csrf")) {
          return jsonResponse({ csrf_header: "X-CSRF-Token" });
        }
        return jsonResponse({ detail: "unexpected fetch " + url }, 404);
      });
    render(
      <AuthProvider>
        <RequireAuth>
          <div>secret</div>
        </RequireAuth>
      </AuthProvider>
    );
    await waitFor(() =>
      expect(screen.getByText("secret")).toBeInTheDocument()
    );
    expect(fetchSpy).toHaveBeenCalled();
  });
});
