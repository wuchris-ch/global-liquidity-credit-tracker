"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";
import { Area, AreaChart, CartesianGrid, Line, LineChart, XAxis, YAxis, ReferenceLine } from "recharts";
import { cn } from "@/lib/utils";

interface ChartDataPoint {
  date: string;
  value: number;
  [key: string]: string | number;
}

// Smart date formatter based on data range
function getDateFormatter(data: ChartDataPoint[]) {
  if (data.length < 2) {
    return (value: string) => {
      const date = new Date(value);
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    };
  }

  const firstDate = new Date(data[0].date);
  const lastDate = new Date(data[data.length - 1].date);
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

interface LiquidityChartProps {
  title: string;
  description?: string;
  data: ChartDataPoint[];
  dataKey?: string;
  chartType?: "line" | "area";
  color?: string;
  showGrid?: boolean;
  showYAxis?: boolean;
  height?: number;
  /** Minimum height on mobile screens */
  mobileHeight?: number;
  className?: string;
  valueFormatter?: (value: number) => string;
  referenceLine?: number;
  referenceLabel?: string;
  /** Info tooltip content - displays (i) icon when provided */
  info?: InfoTooltipProps;
}

export function LiquidityChart({
  title,
  description,
  data,
  dataKey = "value",
  chartType = "area",
  color = "var(--chart-1)",
  showGrid = true,
  showYAxis = true,
  height = 300,
  mobileHeight,
  className,
  valueFormatter = (v) => v.toLocaleString(),
  referenceLine,
  referenceLabel,
  info,
}: LiquidityChartProps) {
  // Use mobile height on smaller screens
  const effectiveMobileHeight = mobileHeight ?? Math.max(200, height * 0.7);
  const chartConfig = {
    [dataKey]: {
      label: title,
      color: color,
    },
  } satisfies ChartConfig;

  const ChartComponent = chartType === "area" ? AreaChart : LineChart;

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="inline-flex items-center gap-2 text-base font-semibold">
              {title}
              {info && <InfoTooltip {...info} size="sm" />}
            </CardTitle>
            {description && (
              <CardDescription className="text-xs">{description}</CardDescription>
            )}
          </div>
          {data.length > 0 && (
            <div className="text-right">
              <p className="font-mono text-xl font-bold">
                {valueFormatter(data[data.length - 1]?.[dataKey] as number)}
              </p>
              <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Latest
              </p>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="pb-4">
        <ChartContainer 
          config={chartConfig} 
          className="w-full" 
          style={{ 
            height: `clamp(${effectiveMobileHeight}px, 40vw, ${height}px)`,
            minHeight: effectiveMobileHeight,
          }}
        >
          <ChartComponent
            data={data}
            margin={{ top: 10, right: 10, left: showYAxis ? 0 : -20, bottom: 0 }}
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
                tickMargin={8}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                tickFormatter={(value) => {
                  if (value >= 1e12) return `${(value / 1e12).toFixed(1)}T`;
                  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
                  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
                  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
                  return value.toFixed(1);
                }}
                width={50}
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
                  formatter={(value) => [valueFormatter(value as number), title]}
                />
              }
            />
            {referenceLine !== undefined && (
              <ReferenceLine
                y={referenceLine}
                stroke="var(--muted-foreground)"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
                label={{
                  value: referenceLabel,
                  position: "right",
                  fill: "var(--muted-foreground)",
                  fontSize: 10,
                }}
              />
            )}
            {chartType === "area" ? (
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={2}
                fill={`url(#gradient-${dataKey})`}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: color,
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
              />
            ) : (
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={2}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: color,
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
              />
            )}
            <defs>
              <linearGradient id={`gradient-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
          </ChartComponent>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}






