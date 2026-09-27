"use client";

import { useEffect } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Route-level error boundary: catches unexpected render/data failures so the
 * user sees a calm recovery screen instead of a blank page or a stack trace.
 * Internal exception details are logged to the console only — never rendered.
 */
export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <Card className="w-full">
        <CardHeader>
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-5 w-5 text-destructive" aria-hidden="true" />
          </span>
          <CardTitle className="mt-2">Something went wrong</CardTitle>
          <CardDescription>
            An unexpected error occurred. Your data is safe — try again, and if
            the problem persists, return to the dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center gap-3">
          <Button onClick={reset}>
            <RefreshCw className="size-4" aria-hidden="true" /> Try again
          </Button>
          <Button variant="outline" asChild>
            <a href="/">Go to Dashboard</a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
