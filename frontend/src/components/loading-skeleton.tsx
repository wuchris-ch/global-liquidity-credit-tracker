"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

// Deterministic bar heights to avoid impure Math.random calls during render.
const BAR_HEIGHTS = Array.from({ length: 30 }, (_, i) => 20 + ((i * 13) % 60));

export function MetricCardSkeleton() {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}

export function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-60" />
          </div>
          <div className="text-right space-y-1">
            <Skeleton className="h-6 w-24 ml-auto" />
            <Skeleton className="h-3 w-12 ml-auto" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-4">
        <div
          className="relative w-full overflow-hidden rounded-lg bg-muted/30"
          style={{ height }}
        >
          <div className="absolute inset-0 flex items-end justify-around gap-1 p-4">
            {BAR_HEIGHTS.map((barHeight, i) => (
              <div
                key={i}
                className="w-full bg-muted animate-pulse"
                style={{
                  height: `${barHeight}%`,
                  animationDelay: `${i * 50}ms`,
                }}
              />
            ))}
          </div>
          <div className="absolute inset-0 bg-gradient-to-t from-card to-transparent" />
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* Metrics Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricCardSkeleton key={i} />
        ))}
      </div>

      {/* Charts Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartSkeleton height={320} />
        <ChartSkeleton height={320} />
      </div>

      {/* Bottom Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartSkeleton height={250} />
        <ChartSkeleton height={250} />
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <Skeleton className="h-4 w-4 rounded-full" />
                <Skeleton className="h-4 w-32" />
              </div>
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}










