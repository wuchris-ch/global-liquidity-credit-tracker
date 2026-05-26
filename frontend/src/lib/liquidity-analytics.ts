import type { DataPoint } from "@/lib/api";
import type { TimeRange } from "@/components/header";
import { getDateRange } from "@/lib/utils";

export interface PeriodChange {
  current: number;
  prior: number;
  deltaAbs: number;
  deltaPct: number;
}

export interface NetLiquidityEquityPoint {
  date: string;
  netLiquidity: number;
  sp500: number;
}

/** Ensure enough history for rolling stats (e.g. 52-week correlation). */
export function getLiquidityAnalyticsRange(
  timeRange: TimeRange,
  minWeeks = 56
): { start: string; end: string } {
  const display = getDateRange(timeRange);
  const floor = new Date();
  floor.setDate(floor.getDate() - minWeeks * 7);
  const floorIso = floor.toISOString().split("T")[0];
  const startMs = Math.min(
    new Date(display.start).getTime(),
    new Date(floorIso).getTime()
  );
  return {
    start: new Date(startMs).toISOString().split("T")[0],
    end: display.end,
  };
}

export function scaleNetLiquidity(
  data: DataPoint[],
  scaleMillions: number
): DataPoint[] {
  return data.map((d) => ({ ...d, value: d.value * scaleMillions }));
}

/** Week-over-week (or step) change using N observations back (weekly data: periods=4 → ~4 weeks). */
export function periodChange(
  data: DataPoint[],
  periods: number,
  valueScale = 1
): PeriodChange | null {
  if (data.length <= periods) return null;
  const current = (data[data.length - 1]?.value ?? 0) * valueScale;
  const prior = (data[data.length - 1 - periods]?.value ?? 0) * valueScale;
  const deltaAbs = current - prior;
  const deltaPct = prior !== 0 ? (deltaAbs / prior) * 100 : 0;
  return { current, prior, deltaAbs, deltaPct };
}

/** Align weekly net liquidity with last available equity print on or before each date. */
export function mergeNetLiquidityWithEquity(
  netLiquidity: DataPoint[],
  equity: DataPoint[],
  netLiquidityScale: number
): NetLiquidityEquityPoint[] {
  if (netLiquidity.length === 0 || equity.length === 0) return [];

  const sortedEquity = [...equity].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  let eqIdx = 0;
  const merged: NetLiquidityEquityPoint[] = [];

  for (const row of netLiquidity) {
    const t = new Date(row.date).getTime();
    while (
      eqIdx + 1 < sortedEquity.length &&
      new Date(sortedEquity[eqIdx + 1].date).getTime() <= t
    ) {
      eqIdx += 1;
    }
    if (new Date(sortedEquity[eqIdx].date).getTime() > t) continue;

    merged.push({
      date: row.date,
      netLiquidity: row.value * netLiquidityScale,
      sp500: sortedEquity[eqIdx].value,
    });
  }

  return merged;
}

function pctChanges(values: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < values.length; i++) {
    const prev = values[i - 1];
    if (prev === 0) continue;
    out.push((values[i] - prev) / prev);
  }
  return out;
}

function pearson(xs: number[], ys: number[]): number | null {
  const n = Math.min(xs.length, ys.length);
  if (n < 8) return null;
  const x = xs.slice(-n);
  const y = ys.slice(-n);
  const meanX = x.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let denX = 0;
  let denY = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }
  const den = Math.sqrt(denX * denY);
  if (den === 0) return null;
  return num / den;
}

/** Rolling correlation of weekly % changes (default 52 weeks). */
export function rollingWeeklyChangeCorrelation(
  merged: NetLiquidityEquityPoint[],
  windowWeeks = 52
): number | null {
  if (merged.length < windowWeeks + 1) {
    return pearson(
      pctChanges(merged.map((d) => d.netLiquidity)),
      pctChanges(merged.map((d) => d.sp500))
    );
  }
  const slice = merged.slice(-(windowWeeks + 1));
  return pearson(
    pctChanges(slice.map((d) => d.netLiquidity)),
    pctChanges(slice.map((d) => d.sp500))
  );
}

export function formatCorrelation(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "N/A";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

export function correlationInterpretation(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "Insufficient overlapping history";
  const abs = Math.abs(value);
  if (abs >= 0.5) return "Weekly changes in net liquidity and equities have moved together recently.";
  if (abs >= 0.25) return "Moderate co-movement of weekly changes; use with other indicators.";
  return "Weak recent co-movement; liquidity flow may not be driving equities in this window.";
}

/** 4-week change series for charting (weekly steps). */
export function netLiquidityFlowSeries(
  scaledNetLiq: DataPoint[],
  periods = 4
): DataPoint[] {
  const out: DataPoint[] = [];
  for (let i = periods; i < scaledNetLiq.length; i++) {
    const cur = scaledNetLiq[i].value;
    const prev = scaledNetLiq[i - periods].value;
    out.push({
      date: scaledNetLiq[i].date,
      value: cur - prev,
    });
  }
  return out;
}
