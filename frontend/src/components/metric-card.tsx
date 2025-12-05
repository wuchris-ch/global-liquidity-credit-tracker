"use client";

import { Card, CardContent } from "@/components/ui/card";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";
import { cn } from "@/lib/utils";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string;
  change?: number;
  changeLabel?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
  className?: string;
  variant?: "default" | "highlight" | "compact";
  /** Info tooltip content - displays (i) icon when provided */
  info?: InfoTooltipProps;
}

export function MetricCard({
  title,
  value,
  change,
  changeLabel,
  trend = "neutral",
  icon,
  className,
  variant = "default",
  info,
}: MetricCardProps) {
  const getTrendColor = () => {
    switch (trend) {
      case "up":
        return "text-positive";
      case "down":
        return "text-negative";
      default:
        return "text-muted-foreground";
    }
  };

  const getTrendIcon = () => {
    switch (trend) {
      case "up":
        return <TrendingUp className="h-3 w-3" />;
      case "down":
        return <TrendingDown className="h-3 w-3" />;
      default:
        return <Minus className="h-3 w-3" />;
    }
  };

  if (variant === "compact") {
    return (
      <div className={cn("flex items-center justify-between py-2", className)}>
        <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
          {title}
          {info && <InfoTooltip {...info} size="xs" />}
        </span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold">{value}</span>
          {change !== undefined && (
            <span className={cn("flex items-center gap-0.5 font-mono text-xs", getTrendColor())}>
              {getTrendIcon()}
              {Math.abs(change).toFixed(2)}%
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <Card
      className={cn(
        "group relative overflow-hidden transition-all duration-300 hover:border-primary/30",
        variant === "highlight" && "border-primary/20 bg-gradient-to-br from-card to-primary/5",
        className
      )}
    >
      {variant === "highlight" && (
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      )}
      <CardContent className="relative p-3 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1 sm:space-y-2 min-w-0 flex-1">
            <p className="inline-flex items-center gap-1 text-[9px] sm:text-[11px] font-semibold uppercase tracking-widest text-muted-foreground truncate">
              {title}
              {info && <InfoTooltip {...info} size="xs" />}
            </p>
            <p className="font-mono text-lg sm:text-2xl font-bold tracking-tight truncate">{value}</p>
            {(change !== undefined || changeLabel) && (
              <div className={cn("flex items-center gap-1 font-mono text-[10px] sm:text-xs", getTrendColor())}>
                {getTrendIcon()}
                <span className="font-medium truncate">
                  {change !== undefined && `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                  {changeLabel && ` ${changeLabel}`}
                </span>
              </div>
            )}
          </div>
          {icon && (
            <div className="hidden sm:flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted/50 text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
              {icon}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}






