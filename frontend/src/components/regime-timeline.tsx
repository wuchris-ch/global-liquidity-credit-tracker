"use client";

import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { InfoTooltip } from "@/components/info-tooltip";
import { regimeDefinitions } from "@/lib/indicator-definitions";
import { cn } from "@/lib/utils";

interface RegimePeriod {
  regime: string;
  start: string;
  end: string;
}

interface RegimeTimelineProps {
  periods: RegimePeriod[];
  currentRegime?: string;
  className?: string;
}

const regimeColors = {
  loose: {
    bg: "bg-emerald-500",
    bgLight: "bg-emerald-500/20",
    border: "border-emerald-500/50",
    text: "text-emerald-500",
  },
  neutral: {
    bg: "bg-amber-500",
    bgLight: "bg-amber-500/20",
    border: "border-amber-500/50",
    text: "text-amber-500",
  },
  tight: {
    bg: "bg-red-500",
    bgLight: "bg-red-500/20",
    border: "border-red-500/50",
    text: "text-red-500",
  },
};

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function getDurationWeeks(start: string, end: string): number {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const diffTime = Math.abs(endDate.getTime() - startDate.getTime());
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24 * 7));
}

export function RegimeTimeline({ periods, currentRegime, className }: RegimeTimelineProps) {
  const totalWeeks = useMemo(() => {
    if (periods.length === 0) return 1;
    const start = new Date(periods[0].start);
    const end = new Date(periods[periods.length - 1].end);
    return Math.max(getDurationWeeks(start.toISOString(), end.toISOString()), 1);
  }, [periods]);

  const segmentsWithWidth = useMemo(() => {
    return periods.map((period) => {
      const weeks = getDurationWeeks(period.start, period.end);
      const widthPct = Math.max((weeks / totalWeeks) * 100, 1);
      return { ...period, weeks, widthPct };
    });
  }, [periods, totalWeeks]);

  // Calculate regime stats
  const regimeStats = useMemo(() => {
    const stats: Record<string, number> = { loose: 0, neutral: 0, tight: 0 };
    periods.forEach((p) => {
      const weeks = getDurationWeeks(p.start, p.end);
      stats[p.regime] = (stats[p.regime] || 0) + weeks;
    });
    return stats;
  }, [periods]);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="inline-flex items-center gap-2 text-base font-semibold">
              Regime History
              <InfoTooltip {...regimeDefinitions.regime_history} size="sm" />
            </CardTitle>
            <CardDescription className="text-xs">
              Historical liquidity regime classification
            </CardDescription>
          </div>
          {currentRegime && (
            <div className={cn(
              "rounded-full px-3 py-1 text-xs font-semibold capitalize",
              regimeColors[currentRegime as keyof typeof regimeColors]?.bgLight,
              regimeColors[currentRegime as keyof typeof regimeColors]?.text
            )}>
              {currentRegime}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Timeline bar */}
        <div className="relative">
          <div className="flex h-8 w-full overflow-hidden rounded-lg">
            {segmentsWithWidth.map((segment, idx) => {
              const colors = regimeColors[segment.regime as keyof typeof regimeColors] || regimeColors.neutral;
              
              return (
                <Tooltip key={idx}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "h-full cursor-pointer transition-opacity hover:opacity-80",
                        colors.bg,
                        idx === segmentsWithWidth.length - 1 && "rounded-r-lg",
                        idx === 0 && "rounded-l-lg"
                      )}
                      style={{ width: `${segment.widthPct}%` }}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="space-y-1">
                      <p className="font-semibold capitalize">{segment.regime}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(segment.start)} – {formatDate(segment.end)}
                      </p>
                      <p className="text-xs">
                        {segment.weeks} weeks
                      </p>
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
          
          {/* Date labels */}
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
            {periods.length > 0 && (
              <>
                <span>{formatDate(periods[0].start)}</span>
                <span>{formatDate(periods[periods.length - 1].end)}</span>
              </>
            )}
          </div>
        </div>

        {/* Regime distribution */}
        <div className="grid grid-cols-3 gap-3">
          {(["loose", "neutral", "tight"] as const).map((regime) => {
            const colors = regimeColors[regime];
            const weeks = regimeStats[regime] || 0;
            const pct = totalWeeks > 0 ? (weeks / totalWeeks * 100).toFixed(0) : 0;

            return (
              <div
                key={regime}
                className={cn(
                  "rounded-lg border p-3 text-center",
                  colors.border,
                  colors.bgLight
                )}
              >
                <p className={cn("text-lg font-bold", colors.text)}>{pct}%</p>
                <p className="text-xs capitalize text-muted-foreground">{regime}</p>
                <p className="text-[10px] text-muted-foreground">{weeks}w</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

interface RegimeBadgeProps {
  regime: string;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function RegimeBadge({ regime, size = "md", showLabel = true }: RegimeBadgeProps) {
  const colors = regimeColors[regime as keyof typeof regimeColors] || regimeColors.neutral;
  
  const sizeClasses = {
    sm: "h-2 w-2",
    md: "h-3 w-3",
    lg: "h-4 w-4",
  };

  const textSizes = {
    sm: "text-xs",
    md: "text-sm",
    lg: "text-base",
  };

  return (
    <div className="flex items-center gap-2">
      <div className={cn("rounded-full", sizeClasses[size], colors.bg)} />
      {showLabel && (
        <span className={cn("font-medium capitalize", textSizes[size], colors.text)}>
          {regime}
        </span>
      )}
    </div>
  );
}

