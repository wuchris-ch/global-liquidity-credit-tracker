"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { InfoTooltip, InfoTooltipProps } from "@/components/info-tooltip";
import { Bar, BarChart, Cell, ReferenceLine, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/utils";

interface WaterfallDataPoint {
  name: string;
  value: number;
  isTotal?: boolean;
  fill?: string;
}

interface WaterfallChartProps {
  title: string;
  description?: string;
  previousValue: number;
  currentValue: number;
  contributions: {
    name: string;
    value: number;
    color?: string;
  }[];
  height?: number;
  /** Minimum height on mobile screens */
  mobileHeight?: number;
  className?: string;
  /** Info tooltip content - displays (i) icon when provided */
  info?: InfoTooltipProps;
}

const pillarColors = {
  liquidity: "var(--pillar-liquidity)",
  credit: "var(--pillar-credit)",
  stress: "var(--pillar-stress)",
};

export function WaterfallChart({
  title,
  description,
  previousValue,
  currentValue,
  contributions,
  height = 200,
  mobileHeight,
  className,
  info,
}: WaterfallChartProps) {
  // Use mobile height on smaller screens
  const effectiveMobileHeight = mobileHeight ?? Math.max(180, height * 0.75);
  // Build waterfall data
  const data: WaterfallDataPoint[] = [
    { name: "Previous", value: previousValue, isTotal: true, fill: "var(--muted-foreground)" },
    ...contributions.map((c) => ({
      name: c.name.charAt(0).toUpperCase() + c.name.slice(1),
      value: c.value,
      fill: c.color || pillarColors[c.name as keyof typeof pillarColors] || "var(--primary)",
    })),
    { name: "Current", value: currentValue, isTotal: true, fill: "var(--primary)" },
  ];

  // Calculate cumulative values for waterfall positioning
  let cumulative = previousValue;
  const waterfallData = data.map((item, index) => {
    if (index === 0) {
      return { ...item, start: 0, end: item.value };
    }
    if (item.isTotal) {
      return { ...item, start: 0, end: item.value };
    }
    const start = cumulative;
    cumulative += item.value;
    return { ...item, start: Math.min(start, cumulative), end: Math.max(start, cumulative) };
  });

  const chartConfig = {
    value: {
      label: "Change",
    },
  } satisfies ChartConfig;

  const totalChange = currentValue - previousValue;
  const changeColor = totalChange >= 0 ? "text-positive" : "text-negative";

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
          <div className="text-right">
            <p className={cn("font-mono text-lg font-bold", changeColor)}>
              {totalChange >= 0 ? "+" : ""}{totalChange.toFixed(2)}
            </p>
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Weekly Change
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-4">
        <ChartContainer 
          config={chartConfig} 
          className="w-full" 
          style={{ 
            height: `clamp(${effectiveMobileHeight}px, 35vw, ${height}px)`,
            minHeight: effectiveMobileHeight,
          }}
        >
          <BarChart
            data={waterfallData}
            layout="vertical"
            margin={{ top: 10, right: 20, left: 60, bottom: 10 }}
          >
            <XAxis
              type="number"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              domain={['auto', 'auto']}
            />
            <YAxis
              type="category"
              dataKey="name"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
              width={55}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  className="border-border bg-popover/95 backdrop-blur-sm"
                  formatter={(value, name, item) => {
                    const dataItem = item.payload;
                    if (dataItem.isTotal) {
                      return [`${Number(value).toFixed(2)}`, "Value"];
                    }
                    return [
                      `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}`,
                      "Contribution"
                    ];
                  }}
                />
              }
            />
            <ReferenceLine x={previousValue} stroke="var(--border)" strokeDasharray="3 3" />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {waterfallData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.fill}
                  opacity={entry.isTotal ? 1 : 0.85}
                />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}

interface ContributionBreakdownProps {
  pillars: {
    name: string;
    value: number;
    weight: number;
    contribution: number;
  }[];
  className?: string;
  /** Optional info tooltips for each pillar by name */
  pillarInfo?: Record<string, InfoTooltipProps>;
}

export function ContributionBreakdown({ pillars, className, pillarInfo }: ContributionBreakdownProps) {
  const totalContribution = pillars.reduce((sum, p) => sum + p.contribution, 0);

  return (
    <div className={cn("space-y-3", className)}>
      {pillars.map((pillar) => {
        const color = pillarColors[pillar.name as keyof typeof pillarColors] || "var(--primary)";
        const pctOfTotal = totalContribution !== 0 
          ? Math.abs(pillar.contribution / totalContribution) * 100 
          : 0;
        const info = pillarInfo?.[pillar.name];

        return (
          <div key={pillar.name} className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="inline-flex items-center gap-1.5 font-medium capitalize">
                  {pillar.name}
                  {info && <InfoTooltip {...info} size="xs" />}
                </span>
                <span className="text-xs text-muted-foreground">
                  ({(pillar.weight * 100).toFixed(0)}% wt)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">
                  {pillar.value >= 0 ? "+" : ""}{pillar.value.toFixed(2)}
                </span>
                <span className={cn(
                  "font-mono text-sm font-semibold",
                  pillar.contribution >= 0 ? "text-positive" : "text-negative"
                )}>
                  {pillar.contribution >= 0 ? "+" : ""}{pillar.contribution.toFixed(2)}
                </span>
              </div>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(pctOfTotal, 100)}%`,
                  backgroundColor: color,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

