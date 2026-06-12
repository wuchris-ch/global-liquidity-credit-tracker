"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { isStaticMode } from "@/lib/api";

interface DataLoadErrorProps {
  title?: string;
  onRetry?: () => void;
}

/**
 * Mode-aware data-load error state. In production (static data on GitHub
 * Pages) a fetch failure means the CDN was unreachable — telling the user
 * to start a local Python backend would be misleading, so that hint is
 * shown only in local API mode.
 */
export function DataLoadError({ title = "Failed to Load Data", onRetry }: DataLoadErrorProps) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Card className="max-w-md">
        <CardContent className="flex flex-col items-center gap-4 p-6">
          <AlertCircle className="h-12 w-12 text-destructive" />
          <h2 className="text-lg font-semibold">{title}</h2>
          {isStaticMode ? (
            <p className="text-center text-sm text-muted-foreground">
              The published data feed could not be reached. This is usually
              temporary — check your connection and try again.
            </p>
          ) : (
            <>
              <p className="text-center text-sm text-muted-foreground">
                Could not connect to the local data API. Make sure the Python
                backend is running:
              </p>
              <code className="rounded bg-muted px-3 py-2 text-sm">
                uvicorn src.api:app --reload --port 8000
              </code>
            </>
          )}
          {onRetry && (
            <Button variant="outline" size="sm" className="gap-2" onClick={onRetry}>
              <RefreshCw className="h-4 w-4" />
              Try again
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
