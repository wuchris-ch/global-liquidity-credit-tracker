"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";
import { CartesianGrid, Line, LineChart, XAxis, YAxis, Legend } from "recharts";
import { cn } from "@/lib/utils";

interface SeriesConfig {
  key: string;
  label: string;
  color: string;
}

// Smart date formatter based on data range
function getDateFormatter(data: Record<string, string | number>[]) {
  if (data.length < 2) {
    return (value: string) => {
      const date = new Date(value);
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    };
  }

  const firstDate = new Date(data[0].date as string);
  const lastDate = new Date(data[data.length - 1].date as string);
  const daysDiff = Math.abs(
    (lastDate.getTime() - firstDate.getTime()) / (1000 * 60 * 60 * 24)
  );

  // For ranges > 2 years, show "MMM 'YY" format
  if (daysDiff > 730) {
    return (value: string) => {
      const date = new Date(value);
      const month = date.toLocaleDateString("en-US", { month: "short" });
      const year = date.getFullYear().toString().slice(-2);
      return `${month} '${year}`;
    };
  }

  // For ranges > 6 months, show "MMM YYYY" format
  if (daysDiff > 180) {
    return (value: string) => {
      const date = new Date(value);
      return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
    };
  }

  // For shorter ranges, show "MMM D" format
  return (value: string) => {
    const date = new Date(value);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };
}

interface MultiLineChartProps {
  title: string;
  description?: string;
  data: Record<string, string | number>[];
  series: SeriesConfig[];
  showGrid?: boolean;
  showYAxis?: boolean;
  showLegend?: boolean;
  height?: number;
  /** Minimum height on mobile screens */
  mobileHeight?: number;
  className?: string;
  valueFormatter?: (value: number) => string;
  normalized?: boolean;
  /** Info tooltip content - displays (i) icon when provided */
  info?: InfoTooltipProps;
}

export function MultiLineChart({
  title,
  description,
  data,
  series,
  showGrid = true,
  showYAxis = true,
  showLegend = true,
  height = 300,
  mobileHeight,
  className,
  valueFormatter = (v) => v.toLocaleString(),
  normalized = false,
  info,
}: MultiLineChartProps) {
  // Use mobile height on smaller screens
  const effectiveMobileHeight = mobileHeight ?? Math.max(200, height * 0.7);
  const chartConfig = series.reduce((acc, s) => {
    acc[s.key] = {
      label: s.label,
      color: s.color,
    };
    return acc;
  }, {} as ChartConfig);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-2 px-3 sm:px-6">
        <CardTitle className="inline-flex items-center gap-1.5 text-sm sm:text-base font-semibold">
          <span className="truncate">{title}</span>
          {info && <InfoTooltip {...info} size="sm" />}
        </CardTitle>
        {description && (
          <CardDescription className="text-[10px] sm:text-xs truncate">{description}</CardDescription>
        )}
      </CardHeader>
      <CardContent className="pb-3 px-2 sm:px-6 sm:pb-4">
        <ChartContainer 
          config={chartConfig} 
          className="w-full" 
          style={{ 
            height: `clamp(${effectiveMobileHeight}px, 40vw, ${height}px)`,
            minHeight: effectiveMobileHeight,
          }}
        >
          <LineChart
            data={data}
            margin={{ top: 5, right: 5, left: showYAxis ? -10 : -25, bottom: 0 }}
          >
            {showGrid && (
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                stroke="var(--border)"
                strokeOpacity={0.5}
              />
            )}
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={40}
              tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              tickFormatter={getDateFormatter(data)}
            />
            {showYAxis && (
              <YAxis
                tickLine={false}
                axisLine={false}
                tickMargin={4}
                tick={{ fill: "var(--muted-foreground)", fontSize: 9 }}
                tickFormatter={(value) => {
                  if (normalized) return value.toFixed(0);
                  if (value >= 1e12) return `${(value / 1e12).toFixed(1)}T`;
                  if (value >= 1e9) return `${(value / 1e9).toFixed(0)}B`;
                  if (value >= 1e6) return `${(value / 1e6).toFixed(0)}M`;
                  if (value >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
                  return value.toFixed(1);
                }}
                width={40}
              />
            )}
            <ChartTooltip
              content={
                <ChartTooltipContent
                  className="border-border bg-popover/95 backdrop-blur-sm"
                  labelFormatter={(value) => {
                    return new Date(value).toLocaleDateString("en-US", {
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    });
                  }}
                />
              }
            />
            {showLegend && (
              <Legend
                verticalAlign="top"
                align="right"
                wrapperStyle={{
                  paddingBottom: "5px",
                  fontSize: "9px",
                }}
              />
            )}
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: s.color,
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
              />
            ))}
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}






