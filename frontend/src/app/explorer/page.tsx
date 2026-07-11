"use client";

import { useCallback, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartSection } from "@/components/chart-section";
import { RangeTabs } from "@/components/range-tabs";
import { useMultipleSeries, useSeriesList } from "@/hooks/use-series-data";
import {
  AXIS_LINE,
  AXIS_TICK,
  GRID_PROPS,
  TOOLTIP_LABEL_STYLE,
  TOOLTIP_STYLE,
  formatTickDate,
  formatTooltipDate,
} from "@/lib/chart-theme";
import { getDateRange, type TimeRange } from "@/lib/utils";
import type { SeriesInfo } from "@/lib/api";

const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--pillar-stress)",
  "var(--chart-3)",
  "var(--pillar-credit)",
];

const MAX_SERIES = 5;

interface Preset {
  label: string;
  ids: string[];
  normalize: boolean;
}

const PRESETS: Preset[] = [
  { label: "S&P 500 vs Bitcoin", ids: ["sp500_price", "bitcoin_price"], normalize: true },
  { label: "HY vs IG spreads", ids: ["ice_bofa_us_high_yield_spread", "ice_bofa_us_ig_spread"], normalize: false },
  { label: "Central bank balance sheets", ids: ["fed_total_assets", "ecb_total_assets", "boj_total_assets"], normalize: true },
  { label: "Gold vs Fed assets", ids: ["gold_price", "fed_total_assets"], normalize: true },
  { label: "Funding rates", ids: ["sofr", "fed_funds_rate", "euro_short_term_rate"], normalize: false },
];

const CHART_HEIGHT = 380;

function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatValue(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function PickerSkeleton() {
  return (
    <div className="mt-3 animate-pulse space-y-2" aria-label="Loading the series list">
      <div className="h-9 w-full max-w-md rounded bg-muted" />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="h-8 w-full rounded bg-muted" />
      ))}
    </div>
  );
}

export default function ExplorerPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [normalize, setNormalize] = useState(true);
  const [range, setRange] = useState<TimeRange>("2y");

  const dateRange = useMemo(() => getDateRange(range), [range]);

  const { series: availableSeries, isLoading: listLoading, error: listError } = useSeriesList();
  const { data: seriesData, isLoading: dataLoading } = useMultipleSeries(selected, {
    ...dateRange,
    enabled: selected.length > 0,
  });

  const byId = useMemo(() => {
    const m = new Map<string, SeriesInfo>();
    for (const s of availableSeries) m.set(s.id, s);
    return m;
  }, [availableSeries]);

  /** Presets restricted to series the catalog actually offers. */
  const presets = useMemo(() => {
    if (availableSeries.length === 0) return [];
    return PRESETS.map((p) => ({ ...p, ids: p.ids.filter((id) => byId.has(id)) })).filter(
      (p) => p.ids.length >= 2
    );
  }, [availableSeries.length, byId]);

  const applyPreset = useCallback((preset: Preset) => {
    setSelected(preset.ids.slice(0, MAX_SERIES));
    setNormalize(preset.normalize);
  }, []);

  const toggleSeries = useCallback((id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((s) => s !== id);
      if (prev.length >= MAX_SERIES) return prev;
      return [...prev, id];
    });
  }, []);

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? availableSeries.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.id.toLowerCase().includes(q) ||
            s.category.toLowerCase().includes(q)
        )
      : availableSeries;
    const groups = new Map<string, SeriesInfo[]>();
    for (const s of filtered) {
      const list = groups.get(s.category);
      if (list) list.push(s);
      else groups.set(s.category, [s]);
    }
    return Array.from(groups.entries());
  }, [availableSeries, query]);

  const chartData = useMemo(() => {
    if (selected.length === 0) return [];
    const dates = new Set<string>();
    const valueMaps = new Map<string, Map<string, number>>();
    const bases = new Map<string, number>();
    for (const id of selected) {
      const points = seriesData[id] ?? [];
      const m = new Map<string, number>();
      for (const p of points) {
        m.set(p.date, p.value);
        dates.add(p.date);
      }
      valueMaps.set(id, m);
      const firstNonZero = points.find((p) => p.value !== 0);
      bases.set(id, firstNonZero?.value ?? 1);
    }
    return Array.from(dates)
      .sort()
      .map((date) => {
        const row: Record<string, string | number> = { date };
        for (const id of selected) {
          const v = valueMaps.get(id)?.get(date);
          if (v != null) {
            row[id] = normalize ? (v / (bases.get(id) ?? 1)) * 100 : v;
          }
        }
        return row;
      });
  }, [selected, seriesData, normalize]);

  /** Selected series that came back with no points in this window (fetch failed or no coverage). */
  const emptySeries = useMemo(() => {
    if (dataLoading || selected.length === 0) return [];
    return selected.filter((id) => (seriesData[id] ?? []).length === 0);
  }, [selected, seriesData, dataLoading]);

  const sourceLine = useMemo(() => {
    if (selected.length === 0) return undefined;
    const sources = Array.from(new Set(selected.map((id) => byId.get(id)?.source).filter(Boolean)));
    const base = sources.length > 0 ? `Source: ${sources.join(", ")}.` : undefined;
    const scale = normalize
      ? "Each series indexed to 100 at its first observation in the window."
      : "Raw values; mixed units share one axis.";
    return [base, scale].filter(Boolean).join(" ");
  }, [selected, byId, normalize]);

  const handleExportCsv = useCallback(() => {
    if (selected.length === 0) return;
    const byDate = new Map<string, Record<string, number>>();
    for (const id of selected) {
      for (const point of seriesData[id] ?? []) {
        const row = byDate.get(point.date) ?? {};
        row[id] = point.value;
        byDate.set(point.date, row);
      }
    }
    const dates = Array.from(byDate.keys()).sort();
    const escape = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
    const header = ["date", ...selected.map((id) => escape(byId.get(id)?.name ?? id))];
    const lines = [header.join(",")];
    for (const date of dates) {
      const row = byDate.get(date)!;
      lines.push([date, ...selected.map((id) => row[id] ?? "")].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `explorer-${dateRange.start}-to-${dateRange.end}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [selected, seriesData, byId, dateRange]);

  const atLimit = selected.length >= MAX_SERIES;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          The Explorer
        </span>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          Compare up to five market and macro series.
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          Index each series to 100 for a like-for-like comparison, or inspect the raw values.
        </p>

        {/* Presets */}
        {presets.length > 0 && (
          <div className="mt-7 flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted-foreground">
              Presets
            </span>
            {presets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => applyPreset(preset)}
                className="rounded-sm border border-border bg-transparent px-2.5 py-1 text-xs text-foreground transition-colors hover:border-foreground/40 hover:bg-muted"
              >
                {preset.label}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Series picker */}
      <div className="rule mt-10" />
      <section className="mt-8" aria-label="Series picker">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-sm font-semibold tracking-tight">Pick your series</h2>
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            {selected.length} of {MAX_SERIES} selected
          </span>
        </div>

        {listError ? (
          <p className="mt-3 font-mono text-xs text-negative">
            The series list could not be loaded: {listError.message}
          </p>
        ) : listLoading ? (
          <PickerSkeleton />
        ) : (
          <>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, id, or category"
              aria-label="Search series"
              className="mt-3 w-full max-w-md rounded-sm border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-primary"
            />

            {selected.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {selected.map((id, index) => {
                  const info = byId.get(id);
                  return (
                    <span
                      key={id}
                      className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-card px-2 py-1 text-xs"
                    >
                      <span
                        aria-hidden="true"
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: SERIES_COLORS[index] }}
                      />
                      {info?.name ?? id}
                      <button
                        type="button"
                        onClick={() => toggleSeries(id)}
                        aria-label={`Remove ${info?.name ?? id}`}
                        className="ml-0.5 text-muted-foreground transition-colors hover:text-foreground"
                      >
                        ×
                      </button>
                    </span>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setSelected([])}
                  className="font-mono text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
                >
                  Clear all
                </button>
              </div>
            )}

            <div className="mt-4 max-h-80 overflow-y-auto border-y border-border">
              {grouped.length === 0 ? (
                <p className="py-6 text-center font-serif text-sm italic text-muted-foreground">
                  No series match &ldquo;{query}&rdquo;.
                </p>
              ) : (
                grouped.map(([category, items]) => (
                  <div key={category}>
                    <div className="sticky top-0 border-b border-border bg-background px-1 py-1.5 font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
                      {category}
                    </div>
                    {items.map((s) => {
                      const isSelected = selected.includes(s.id);
                      const colorIndex = selected.indexOf(s.id);
                      const disabled = !isSelected && atLimit;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => toggleSeries(s.id)}
                          disabled={disabled}
                          aria-pressed={isSelected}
                          className={`flex w-full items-baseline justify-between gap-3 border-b border-border px-1 py-2 text-left transition-colors last:border-b-0 ${
                            disabled
                              ? "cursor-not-allowed opacity-40"
                              : isSelected
                                ? "bg-muted/60"
                                : "hover:bg-muted/40"
                          }`}
                        >
                          <span className="flex min-w-0 items-baseline gap-2">
                            {isSelected && (
                              <span
                                aria-hidden="true"
                                className="h-2 w-2 shrink-0 self-center rounded-full"
                                style={{ backgroundColor: SERIES_COLORS[colorIndex] }}
                              />
                            )}
                            <span className="truncate text-sm">{s.name}</span>
                          </span>
                          <span className="shrink-0 font-mono text-[0.6875rem] text-muted-foreground">
                            {s.source} · {s.frequency} · {s.unit}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </section>

      {/* Chart */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Comparison"
        reading={
          selected.length === 0
            ? undefined
            : normalize
              ? "Each series starts the window at 100, so the chart compares relative change. Co-movement does not establish causality or lead-lag."
              : "Raw values share one axis. Switch to indexed view when the units or scales differ."
        }
        source={sourceLine}
        control={
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div role="group" aria-label="Scale" className="flex items-center gap-1 font-mono text-xs">
              {(
                [
                  { value: true, label: "Indexed = 100" },
                  { value: false, label: "Raw" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  aria-pressed={normalize === opt.value}
                  onClick={() => setNormalize(opt.value)}
                  className={`rounded-sm px-2 py-1 transition-colors ${
                    normalize === opt.value
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <RangeTabs value={range} onChange={setRange} />
          </div>
        }
      >
        {selected.length === 0 ? (
          <div
            className="flex items-center justify-center"
            style={{ height: CHART_HEIGHT }}
          >
            <p className="font-serif text-base italic text-muted-foreground">
              Pick a series above, or start from a preset.
            </p>
          </div>
        ) : dataLoading ? (
          <div
            className="animate-pulse rounded bg-muted"
            style={{ height: CHART_HEIGHT }}
            aria-label="Loading chart data"
          />
        ) : (
          <>
            {emptySeries.length > 0 && (
              <p className="mb-2 font-mono text-xs text-negative">
                No data returned in this window for: {emptySeries.map((id) => byId.get(id)?.name ?? id).join(", ")}.
              </p>
            )}
            <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                  tick={AXIS_TICK}
                  tickLine={false}
                  axisLine={false}
                  width={56}
                  domain={["auto", "auto"]}
                  tickFormatter={compactNumber}
                />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  labelStyle={TOOLTIP_LABEL_STYLE}
                  labelFormatter={formatTooltipDate}
                  formatter={(value: number | string, name: string) => [
                    typeof value === "number" ? formatValue(value) : value,
                    name,
                  ]}
                />
                {selected.map((id, index) => (
                  <Line
                    key={id}
                    type="monotone"
                    dataKey={id}
                    name={byId.get(id)?.name ?? id}
                    stroke={SERIES_COLORS[index]}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </ChartSection>

      {/* Window statistics */}
      {selected.length > 0 && !dataLoading && (
        <section className="mt-8" aria-label="Window statistics">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 className="text-sm font-semibold tracking-tight">Over this window</h2>
            <button
              type="button"
              onClick={handleExportCsv}
              className="font-mono text-xs text-primary underline-offset-4 hover:underline"
            >
              Download CSV ↓
            </button>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border font-mono text-[0.6875rem] uppercase tracking-wide text-muted-foreground">
                  <th className="pb-2 text-left font-normal">Series</th>
                  <th className="pb-2 text-right font-normal">Latest</th>
                  <th className="pb-2 text-right font-normal">Min</th>
                  <th className="pb-2 text-right font-normal">Max</th>
                  <th className="pb-2 text-right font-normal">Change</th>
                </tr>
              </thead>
              <tbody>
                {selected.map((id, index) => {
                  const info = byId.get(id);
                  const data = seriesData[id] ?? [];
                  if (data.length === 0) {
                    return (
                      <tr key={id} className="border-b border-border">
                        <td className="py-2.5">
                          <span className="flex items-center gap-2">
                            <span
                              aria-hidden="true"
                              className="h-2 w-2 shrink-0 rounded-full"
                              style={{ backgroundColor: SERIES_COLORS[index] }}
                            />
                            {info?.name ?? id}
                          </span>
                        </td>
                        <td colSpan={4} className="py-2.5 text-right font-mono text-xs text-muted-foreground">
                          no data
                        </td>
                      </tr>
                    );
                  }
                  const first = data[0].value;
                  const latest = data[data.length - 1].value;
                  let min = data[0].value;
                  let max = data[0].value;
                  for (const p of data) {
                    if (p.value < min) min = p.value;
                    if (p.value > max) max = p.value;
                  }
                  const change = first !== 0 ? ((latest - first) / Math.abs(first)) * 100 : null;
                  return (
                    <tr key={id} className="border-b border-border">
                      <td className="py-2.5">
                        <span className="flex items-center gap-2">
                          <span
                            aria-hidden="true"
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: SERIES_COLORS[index] }}
                          />
                          {info?.name ?? id}
                        </span>
                      </td>
                      <td className="py-2.5 text-right font-mono tabular-nums">{formatValue(latest)}</td>
                      <td className="py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                        {formatValue(min)}
                      </td>
                      <td className="py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                        {formatValue(max)}
                      </td>
                      <td
                        className={`py-2.5 text-right font-mono tabular-nums ${
                          change == null
                            ? "text-muted-foreground"
                            : change >= 0
                              ? "text-positive"
                              : "text-negative"
                        }`}
                      >
                        {change == null ? "n/a" : `${change >= 0 ? "+" : "−"}${Math.abs(change).toFixed(1)}%`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 font-mono text-[0.6875rem] text-muted-foreground/80">
            Figures in native units for the selected window. Change is latest vs first observation.
          </p>
        </section>
      )}
    </div>
  );
}
