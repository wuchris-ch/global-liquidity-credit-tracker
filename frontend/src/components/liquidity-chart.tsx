"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import type { DataPoint } from "@/lib/api";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_PROPS,
  TOOLTIP_STYLE,
  TOOLTIP_LABEL_STYLE,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";

/** Compact tick label with a true minus sign for negatives. */
function formatCompactTick(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(0)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(0)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)}K`;
  if (abs >= 100) return `${sign}${abs.toFixed(0)}`;
  return `${sign}${abs % 1 === 0 ? abs.toFixed(0) : abs.toFixed(1)}`;
}

interface LiquidityChartProps {
  /** Used as the tooltip series label. The editorial frame (ChartSection) owns visible titles now. */
  title: string;
  /** Retained for call-site compatibility; not rendered. */
  description?: string;
  data: DataPoint[];
  dataKey?: string;
  /** Retained for call-site compatibility; everything renders as a thin line (no fills/gradients). */
  chartType?: "line" | "area";
  color?: string;
  showGrid?: boolean;
  showYAxis?: boolean;
  height?: number;
  /** Retained for call-site compatibility; height is fixed. */
  mobileHeight?: number;
  className?: string;
  valueFormatter?: (value: number) => string;
  referenceLine?: number;
  referenceLabel?: string;
  /** Retained for call-site compatibility; not rendered. */
  info?: unknown;
}

/**
 * Single-series line on paper: ink line, hairline grid, mono axes.
 * No card chrome — sits inside a ChartSection.
 */
export function LiquidityChart({
  title,
  data,
  dataKey = "value",
  color = "var(--chart-1)",
  showGrid = true,
  showYAxis = true,
  height = 300,
  className,
  valueFormatter = (v) => v.toLocaleString(),
  referenceLine,
  referenceLabel,
}: LiquidityChartProps) {
  return (
    <div style={{ height }} className={cn("w-full", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {showGrid && <CartesianGrid {...GRID_PROPS} />}
          <XAxis
            dataKey="date"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={AXIS_LINE}
            tickFormatter={formatTickDate}
            minTickGap={48}
          />
          {showYAxis && (
            <YAxis
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={48}
              domain={["auto", "auto"]}
              tickFormatter={formatCompactTick}
            />
          )}
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            labelFormatter={(label) => formatTooltipDate(String(label))}
            formatter={(value) => [valueFormatter(Number(value)), title]}
          />
          {referenceLine !== undefined && (
            <ReferenceLine
              y={referenceLine}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              strokeOpacity={0.6}
              label={
                referenceLabel
                  ? {
                      value: referenceLabel,
                      position: "right",
                      fill: "var(--muted-foreground)",
                      fontSize: 10,
                      fontFamily: "var(--font-geist-mono), monospace",
                    }
                  : undefined
              }
            />
          )}
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: color }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
