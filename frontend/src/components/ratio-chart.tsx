"use client";

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { DataPoint, RegimePeriod } from "@/lib/api";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_PROPS,
  TOOLTIP_STYLE,
  TOOLTIP_LABEL_STYLE,
  REGIME_FILL,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";

interface RatioChartProps {
  data: DataPoint[];
  periods?: RegimePeriod[];
  /** Tooltip label for the value, e.g. "BTC / SMH". */
  valueLabel: string;
  /** Horizontal reference (e.g. 100 for an indexed ratio). */
  baseline?: number;
  height?: number;
}

/** Indexed-ratio line on paper with regime washes, in the GLCI chart language. */
export function RatioChart({
  data,
  periods = [],
  valueLabel,
  baseline,
  height = 300,
}: RatioChartProps) {
  // Clamp regime periods to dates present in the data so the category
  // x-axis can place the reference areas (same approach as GlciChart).
  const bands = useMemo(() => {
    if (!data.length || !periods.length) return [];
    const dates = data.map((d) => d.date);
    const first = dates[0];
    const last = dates[dates.length - 1];

    const firstOnOrAfter = (target: string) => {
      for (const d of dates) if (d >= target) return d;
      return null;
    };
    const lastOnOrBefore = (target: string) => {
      for (let i = dates.length - 1; i >= 0; i--) if (dates[i] <= target) return dates[i];
      return null;
    };

    return periods
      .filter((p) => p.end >= first && p.start <= last)
      .map((p) => ({
        regime: p.regime,
        x1: firstOnOrAfter(p.start) ?? first,
        x2: lastOnOrBefore(p.end) ?? last,
      }))
      .filter((b) => b.x1 <= b.x2);
  }, [data, periods]);

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          {bands.map((b, i) => (
            <ReferenceArea
              key={`${b.x1}-${i}`}
              x1={b.x1}
              x2={b.x2}
              fill={REGIME_FILL[b.regime] ?? "transparent"}
              stroke="none"
              ifOverflow="visible"
            />
          ))}
          <XAxis
            dataKey="date"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={AXIS_LINE}
            tickFormatter={formatTickDate}
            minTickGap={48}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={44}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          {baseline != null && (
            <ReferenceLine
              y={baseline}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
          )}
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            labelFormatter={(label) => formatTooltipDate(String(label))}
            formatter={(value) => [Number(value).toFixed(1), valueLabel]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--chart-1)"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: "var(--chart-1)" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
