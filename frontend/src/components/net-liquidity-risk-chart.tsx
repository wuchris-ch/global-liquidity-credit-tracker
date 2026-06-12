"use client";

import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import type { NetLiquidityEquityPoint } from "@/lib/liquidity-analytics";
import { compactDollars } from "@/lib/brief";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_PROPS,
  TOOLTIP_STYLE,
  TOOLTIP_LABEL_STYLE,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";

interface NetLiquidityRiskChartProps {
  /** Merged weekly net liquidity (base dollars) and S&P 500 level. */
  data: NetLiquidityEquityPoint[];
  height?: number;
  className?: string;
}

const NET_LIQ_COLOR = "var(--chart-2)";
const SP500_COLOR = "var(--chart-1)";

/**
 * Dual-axis overlay: net liquidity (left, $T, accent blue) against the
 * S&P 500 (right, ink). Thin lines on paper, legend as small sans text.
 * No card chrome — sits inside a ChartSection.
 */
export function NetLiquidityRiskChart({
  data,
  height = 360,
  className,
}: NetLiquidityRiskChartProps) {
  if (data.length === 0) {
    return (
      <div
        style={{ height }}
        className={cn(
          "flex w-full items-center justify-center font-mono text-xs text-muted-foreground",
          className
        )}
      >
        Not enough overlapping data to plot.
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0.5 w-4" style={{ backgroundColor: NET_LIQ_COLOR }} />
          Net liquidity (left, $T)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0.5 w-4" style={{ backgroundColor: SP500_COLOR }} />
          S&amp;P 500 (right)
        </span>
      </div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID_PROPS} />
            <XAxis
              dataKey="date"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={AXIS_LINE}
              tickFormatter={formatTickDate}
              minTickGap={48}
            />
            <YAxis
              yAxisId="liquidity"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={48}
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => `${(v / 1e12).toFixed(1)}T`}
            />
            <YAxis
              yAxisId="equity"
              orientation="right"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={44}
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0))}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              labelStyle={TOOLTIP_LABEL_STYLE}
              labelFormatter={(label) => formatTooltipDate(String(label))}
              formatter={(value, name) => {
                const v = Number(value);
                if (name === "Net liquidity") return [compactDollars(v), "Net liquidity"];
                return [v.toLocaleString("en-US", { maximumFractionDigits: 0 }), "S&P 500"];
              }}
            />
            <Line
              yAxisId="liquidity"
              type="monotone"
              dataKey="netLiquidity"
              name="Net liquidity"
              stroke={NET_LIQ_COLOR}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0, fill: NET_LIQ_COLOR }}
              isAnimationActive={false}
            />
            <Line
              yAxisId="equity"
              type="monotone"
              dataKey="sp500"
              name="S&P 500"
              stroke={SP500_COLOR}
              strokeWidth={1.25}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0, fill: SP500_COLOR }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
