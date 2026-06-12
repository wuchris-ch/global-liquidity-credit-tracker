"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_PROPS,
  TOOLTIP_STYLE,
  TOOLTIP_LABEL_STYLE,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";

interface SeriesConfig {
  key: string;
  label: string;
  color: string;
}

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

interface MultiLineChartProps {
  /** Retained for call-site compatibility; the editorial frame (ChartSection) owns visible titles now. */
  title?: string;
  /** Retained for call-site compatibility; not rendered. */
  description?: string;
  data: Record<string, string | number>[];
  series: SeriesConfig[];
  showGrid?: boolean;
  showYAxis?: boolean;
  showLegend?: boolean;
  height?: number;
  /** Retained for call-site compatibility; height is fixed. */
  mobileHeight?: number;
  className?: string;
  valueFormatter?: (value: number) => string;
  normalized?: boolean;
  /** Retained for call-site compatibility; not rendered. */
  info?: unknown;
}

/**
 * Multi-series line chart on paper: thin ink lines, hairline grid, mono axes,
 * legend as small sans text. No card chrome — sits inside a ChartSection.
 */
export function MultiLineChart({
  data,
  series,
  showGrid = true,
  showYAxis = true,
  showLegend = true,
  height = 300,
  className,
  valueFormatter,
  normalized = false,
}: MultiLineChartProps) {
  const format = valueFormatter ?? ((v: number) => (normalized ? v.toFixed(0) : formatCompactTick(v)));

  return (
    <div className={cn("space-y-2", className)}>
      {showLegend && series.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block h-0.5 w-4"
                style={{ backgroundColor: s.color }}
              />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <div style={{ height }} className="w-full">
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
                tickFormatter={(v: number) => (normalized ? v.toFixed(0) : formatCompactTick(v))}
              />
            )}
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              labelStyle={TOOLTIP_LABEL_STYLE}
              labelFormatter={(label) => formatTooltipDate(String(label))}
              formatter={(value, name) => [format(Number(value)), String(name)]}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={1.25}
                dot={false}
                activeDot={{ r: 3, strokeWidth: 0, fill: s.color }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
