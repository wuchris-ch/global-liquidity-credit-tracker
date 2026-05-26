"use client";

import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
} from "recharts";
import { cn, formatCurrency } from "@/lib/utils";
import type { NetLiquidityEquityPoint } from "@/lib/liquidity-analytics";
import { formatCorrelation } from "@/lib/liquidity-analytics";

function getDateFormatter(data: NetLiquidityEquityPoint[]) {
  if (data.length < 2) {
    return (value: string) =>
      new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  const firstDate = new Date(data[0].date);
  const lastDate = new Date(data[data.length - 1].date);
  const daysDiff = Math.abs(
    (lastDate.getTime() - firstDate.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (daysDiff > 730) {
    return (value: string) => {
      const date = new Date(value);
      const month = date.toLocaleDateString("en-US", { month: "short" });
      const year = date.getFullYear().toString().slice(-2);
      return `${month} '${year}`;
    };
  }
  if (daysDiff > 180) {
    return (value: string) =>
      new Date(value).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  }
  return (value: string) =>
    new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface NetLiquidityRiskChartProps {
  title: string;
  description?: string;
  data: NetLiquidityEquityPoint[];
  correlation52w: number | null;
  height?: number;
  className?: string;
  info?: InfoTooltipProps;
}

const chartConfig = {
  netLiquidity: {
    label: "Net Liquidity",
    color: "var(--chart-1)",
  },
  sp500: {
    label: "S&P 500",
    color: "var(--chart-4)",
  },
} satisfies ChartConfig;

export function NetLiquidityRiskChart({
  title,
  description,
  data,
  correlation52w,
  height = 420,
  className,
  info,
}: NetLiquidityRiskChartProps) {
  const tickFormatter = useMemo(() => getDateFormatter(data), [data]);
  const mobileHeight = Math.max(240, height * 0.65);

  const corrBadgeVariant =
    correlation52w !== null && correlation52w >= 0.35
      ? "default"
      : correlation52w !== null && correlation52w <= -0.15
        ? "destructive"
        : "secondary";

  return (
    <Card className={cn("overflow-hidden border-primary/20", className)}>
      <CardHeader className="pb-2 px-3 sm:px-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <CardTitle className="inline-flex items-center gap-1.5 text-sm sm:text-base font-semibold">
              <span className="truncate">{title}</span>
              {info && <InfoTooltip {...info} size="sm" />}
            </CardTitle>
            {description && (
              <CardDescription className="text-[10px] sm:text-xs mt-0.5">
                {description}
              </CardDescription>
            )}
          </div>
          <Badge variant={corrBadgeVariant} className="w-fit shrink-0 font-mono text-xs">
            52w Δ corr: {formatCorrelation(correlation52w)}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-3 text-[10px] sm:text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[var(--chart-1)]" />
            Net liquidity (left)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[var(--chart-4)]" />
            S&P 500 (right)
          </span>
        </div>
      </CardHeader>
      <CardContent className="pb-3 px-2 sm:px-6 sm:pb-4">
        {data.length === 0 ? (
          <div
            className="flex items-center justify-center text-sm text-muted-foreground"
            style={{ height: mobileHeight }}
          >
            Not enough data to plot
          </div>
        ) : (
          <ChartContainer
            config={chartConfig}
            className="w-full"
            style={{
              height: `clamp(${mobileHeight}px, 45vw, ${height}px)`,
              minHeight: mobileHeight,
            }}
          >
            <ComposedChart
              data={data}
              margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                stroke="var(--border)"
                strokeOpacity={0.5}
              />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={40}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                tickFormatter={tickFormatter}
              />
              <YAxis
                yAxisId="liquidity"
                tickLine={false}
                axisLine={false}
                tickMargin={4}
                tick={{ fill: "var(--chart-1)", fontSize: 9 }}
                tickFormatter={(v) => {
                  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
                  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
                  return `${(v / 1e6).toFixed(0)}M`;
                }}
                width={44}
              />
              <YAxis
                yAxisId="equity"
                orientation="right"
                tickLine={false}
                axisLine={false}
                tickMargin={4}
                tick={{ fill: "var(--chart-4)", fontSize: 9 }}
                tickFormatter={(v) =>
                  v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)
                }
                width={40}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    className="border-border bg-popover/95 backdrop-blur-sm"
                    labelFormatter={(value) =>
                      new Date(value).toLocaleDateString("en-US", {
                        month: "long",
                        day: "numeric",
                        year: "numeric",
                      })
                    }
                    formatter={(value, name) => {
                      const v = value as number;
                      if (name === "netLiquidity") {
                        return [formatCurrency(v), "Net Liquidity"];
                      }
                      return [v.toLocaleString(undefined, { maximumFractionDigits: 0 }), "S&P 500"];
                    }}
                  />
                }
              />
              <Area
                yAxisId="liquidity"
                type="monotone"
                dataKey="netLiquidity"
                stroke="var(--chart-1)"
                strokeWidth={2}
                fill="url(#gradient-net-liq-risk)"
                dot={false}
                activeDot={{
                  r: 4,
                  fill: "var(--chart-1)",
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
              />
              <Line
                yAxisId="equity"
                type="monotone"
                dataKey="sp500"
                stroke="var(--chart-4)"
                strokeWidth={2}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: "var(--chart-4)",
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
              />
              <defs>
                <linearGradient id="gradient-net-liq-risk" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
            </ComposedChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
