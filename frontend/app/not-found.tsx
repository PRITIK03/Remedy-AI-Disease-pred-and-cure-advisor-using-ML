import Link from "next/link";
import { FileQuestion } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <Card className="w-full">
        <CardHeader>
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-muted">
            <FileQuestion className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          </span>
          <CardTitle className="mt-2">Page not found</CardTitle>
          <CardDescription>
            The page you are looking for does not exist or may have been moved.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center gap-3">
          <Button asChild>
            <Link href="/">Go to Dashboard</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/history">View History</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
