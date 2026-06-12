"use client";

import { useMemo, useState } from "react";
import { useIndexData, useSeriesData } from "@/hooks/use-series-data";
import { ChartSection } from "@/components/chart-section";
import { RangeTabs } from "@/components/range-tabs";
import { DataLoadError } from "@/components/data-load-error";
import { LiquidityChart } from "@/components/liquidity-chart";
import { MultiLineChart } from "@/components/multi-line-chart";
import { NetLiquidityRiskChart } from "@/components/net-liquidity-risk-chart";
import { getDateRange, UNIT_SCALES, type TimeRange } from "@/lib/utils";
import { compactDollars } from "@/lib/brief";
import {
  getLiquidityAnalyticsRange,
  mergeNetLiquidityWithEquity,
  periodChange,
  rollingWeeklyChangeCorrelation,
  scaleNetLiquidity,
  type PeriodChange,
} from "@/lib/liquidity-analytics";
import type { DataPoint } from "@/lib/api";
import type { UseSeriesDataResult } from "@/hooks/use-series-data";

// ---------------------------------------------------------------------------
// Deterministic prose, in the manner of lib/brief.ts: same data in, same
// words out.
// ---------------------------------------------------------------------------

interface DriverChanges {
  /** 4-week changes in base dollars; null when the series is unavailable. */
  fed: number | null;
  tga: number | null;
  rrp: number | null;
}

/**
 * Which component of net liquidity (= Fed assets − TGA − RRP) moved the
 * needle most over the window. Contributions are signed in net-liquidity
 * terms: a falling TGA or RRP adds liquidity.
 */
function driverClause(d: DriverChanges): string | null {
  const candidates: { contribution: number; lift: string; drain: string }[] = [];
  if (d.fed != null)
    candidates.push({
      contribution: d.fed,
      lift: "an expanding Fed balance sheet did most of the lifting",
      drain: "Fed balance-sheet runoff did most of the draining",
    });
  if (d.tga != null)
    candidates.push({
      contribution: -d.tga,
      lift: "a falling Treasury General Account did most of the lifting",
      drain: "a rebuilding Treasury General Account did most of the draining",
    });
  if (d.rrp != null)
    candidates.push({
      contribution: -d.rrp,
      lift: "money leaving the reverse-repo facility did most of the lifting",
      drain: "money parking back at the reverse-repo facility did most of the draining",
    });
  if (candidates.length === 0) return null;
  const top = candidates.reduce((a, b) =>
    Math.abs(b.contribution) > Math.abs(a.contribution) ? b : a
  );
  return top.contribution >= 0 ? top.lift : top.drain;
}

function buildLead(
  level: number | null,
  change4w: PeriodChange | null,
  drivers: DriverChanges
): string | null {
  if (level == null) return null;
  const levelText = compactDollars(level);
  if (!change4w) return `Net liquidity stands at ${levelText}.`;
  if (Math.abs(change4w.deltaAbs) < 2e9) {
    return `Net liquidity is little changed over four weeks at ${levelText}; the pipes are quiet.`;
  }
  const dir = change4w.deltaAbs >= 0 ? "up" : "down";
  const base = `Net liquidity stands at ${levelText}, ${dir} ${compactDollars(
    Math.abs(change4w.deltaAbs)
  )} over four weeks`;
  const clause = driverClause(drivers);
  return clause ? `${base}; ${clause}.` : `${base}.`;
}

function spreadsReading(hyBp: number | null, igBp: number | null): string | undefined {
  if (hyBp == null) return undefined;
  const tone =
    hyBp < 350
      ? "calm by historical standards"
      : hyBp <= 500
        ? "wide enough to keep watching"
        : "stressed by any historical measure";
  const igClause = igBp != null ? ` and investment grade ${Math.round(igBp)}bp` : "";
  return `High-yield is paying ${Math.round(hyBp)}bp over Treasuries${igClause}, ${tone}.`;
}

function stressReading(latest: number | null): string | undefined {
  if (latest == null) return undefined;
  const v = `${latest < 0 ? "−" : "+"}${Math.abs(latest).toFixed(2)}σ`;
  if (latest > 0.5) return `The composite sits at ${v}, tighter than its recent norm.`;
  if (latest < -0.5) return `The composite sits at ${v}, easier than its recent norm.`;
  return `The composite sits at ${v}, close to its recent norm.`;
}

function signedTwo(value: number): string {
  return `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Small data helpers
// ---------------------------------------------------------------------------

function latestOf(data: DataPoint[]): number | null {
  return data.length ? data[data.length - 1].value : null;
}

/** Change over a calendar lookback, in raw series units × scale. */
function changeOverDays(data: DataPoint[], days: number, scale = 1): number | null {
  if (data.length < 2) return null;
  const latest = data[data.length - 1];
  const cutoff = new Date(latest.date);
  cutoff.setDate(cutoff.getDate() - days);
  const target = cutoff.toISOString().slice(0, 10);
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].date <= target) return (latest.value - data[i].value) * scale;
  }
  return null;
}

function scaleSeries(data: DataPoint[], scale: number): DataPoint[] {
  return data.map((d) => ({ date: d.date, value: d.value * scale }));
}

/** Rebase a series to 100 at its first nonzero observation. */
function indexTo100(data: DataPoint[]): DataPoint[] {
  const base = data.find((d) => d.value !== 0);
  if (!base) return [];
  return data.map((d) => ({ date: d.date, value: (d.value / base.value) * 100 }));
}

/**
 * Merge indexed series onto the spine's dates, carrying each other series'
 * last observation on or before that date (handles mixed frequencies).
 */
function mergeOnSpine(
  spine: { key: string; data: DataPoint[] },
  others: { key: string; data: DataPoint[] }[]
): Record<string, string | number>[] {
  const pointers = others.map(() => 0);
  return spine.data.map((row) => {
    const out: Record<string, string | number> = { date: row.date, [spine.key]: row.value };
    others.forEach((o, i) => {
      while (pointers[i] + 1 < o.data.length && o.data[pointers[i] + 1].date <= row.date) {
        pointers[i] += 1;
      }
      if (o.data.length > 0 && o.data[pointers[i]].date <= row.date) {
        out[o.key] = o.data[pointers[i]].value;
      }
    });
    return out;
  });
}

type SectionStatus = "pending" | "error" | "ready";

function statusOf(hook: UseSeriesDataResult): SectionStatus {
  if (hook.error) return "error";
  if (hook.isLoading || hook.data.length === 0) return "pending";
  return "ready";
}

// ---------------------------------------------------------------------------
// Presentational bits
// ---------------------------------------------------------------------------

function SectionSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div
      className="w-full animate-pulse rounded bg-muted"
      style={{ height }}
      aria-hidden="true"
    />
  );
}

function MonoNote({ children }: { children: React.ReactNode }) {
  return <p className="font-mono text-xs text-muted-foreground">{children}</p>;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const M = UNIT_SCALES.millions_usd;
const B = UNIT_SCALES.billions_usd;

export default function PlumbingPage() {
  const [range, setRange] = useState<TimeRange>("2y");
  const dateRange = useMemo(() => getDateRange(range), [range]);
  // Extra history behind the display window so the 52-week correlation holds.
  const analyticsRange = useMemo(() => getLiquidityAnalyticsRange(range), [range]);

  const netLiquidity = useIndexData("fed_net_liquidity", analyticsRange);
  const sp500 = useSeriesData("sp500_price", analyticsRange);
  const fedAssets = useSeriesData("fed_total_assets", dateRange);
  const tga = useSeriesData("fed_treasury_general_account", dateRange);
  const rrp = useSeriesData("fed_reverse_repo", dateRange);
  const hySpread = useSeriesData("ice_bofa_us_high_yield_spread", dateRange);
  const igSpread = useSeriesData("ice_bofa_us_ig_spread", dateRange);
  const stress = useIndexData("usd_funding_stress", dateRange);
  const ecbAssets = useSeriesData("ecb_total_assets", dateRange);
  const bojAssets = useSeriesData("boj_total_assets", dateRange);

  // --- Net liquidity, in base dollars ---------------------------------------
  const netLiqDollars = useMemo(
    () => scaleNetLiquidity(netLiquidity.data, M),
    [netLiquidity.data]
  );
  const netLiqDisplay = useMemo(() => {
    const startMs = new Date(dateRange.start).getTime();
    return netLiqDollars.filter((d) => new Date(d.date).getTime() >= startMs);
  }, [netLiqDollars, dateRange.start]);

  const change4w = useMemo(() => periodChange(netLiquidity.data, 4, M), [netLiquidity.data]);

  const lead = useMemo(() => {
    const level = latestOf(netLiqDollars);
    return buildLead(level, change4w, {
      fed: changeOverDays(fedAssets.data, 28, M),
      tga: changeOverDays(tga.data, 28, M),
      rrp: changeOverDays(rrp.data, 28, B),
    });
  }, [netLiqDollars, change4w, fedAssets.data, tga.data, rrp.data]);

  // --- Net liquidity vs S&P 500 ---------------------------------------------
  const merged = useMemo(
    () => mergeNetLiquidityWithEquity(netLiquidity.data, sp500.data, M),
    [netLiquidity.data, sp500.data]
  );
  const mergedDisplay = useMemo(() => {
    const startMs = new Date(dateRange.start).getTime();
    return merged.filter((d) => new Date(d.date).getTime() >= startMs);
  }, [merged, dateRange.start]);
  const correlation52w = useMemo(() => rollingWeeklyChangeCorrelation(merged, 52), [merged]);

  // --- Credit spreads, in basis points ---------------------------------------
  const spreadsData = useMemo(() => {
    if (hySpread.data.length === 0) return [];
    const igByDate = new Map(igSpread.data.map((d) => [d.date, d.value * 100]));
    return hySpread.data.map((d) => {
      const row: Record<string, string | number> = { date: d.date, highYield: d.value * 100 };
      const ig = igByDate.get(d.date);
      if (ig != null) row.investmentGrade = ig;
      return row;
    });
  }, [hySpread.data, igSpread.data]);

  const latestHyBp = useMemo(() => {
    const v = latestOf(hySpread.data);
    return v != null ? v * 100 : null;
  }, [hySpread.data]);
  const latestIgBp = useMemo(() => {
    const v = latestOf(igSpread.data);
    return v != null ? v * 100 : null;
  }, [igSpread.data]);

  // --- Central banks, indexed to 100 at range start ---------------------------
  const ecbReady = statusOf(ecbAssets) === "ready";
  const bojReady = statusOf(bojAssets) === "ready";

  const centralBankData = useMemo(() => {
    const fedIndexed = indexTo100(fedAssets.data);
    if (fedIndexed.length === 0) return [];
    const others: { key: string; data: DataPoint[] }[] = [];
    if (ecbReady) others.push({ key: "ecb", data: indexTo100(ecbAssets.data) });
    if (bojReady) others.push({ key: "boj", data: indexTo100(bojAssets.data) });
    return mergeOnSpine({ key: "fed", data: fedIndexed }, others);
  }, [fedAssets.data, ecbAssets.data, bojAssets.data, ecbReady, bojReady]);

  const centralBankSeries = useMemo(() => {
    const series = [{ key: "fed", label: "Federal Reserve", color: "var(--chart-1)" }];
    if (ecbReady) series.push({ key: "ecb", label: "ECB", color: "var(--chart-2)" });
    if (bojReady) series.push({ key: "boj", label: "Bank of Japan", color: "var(--chart-4)" });
    return series;
  }, [ecbReady, bojReady]);

  // --- Section statuses -------------------------------------------------------
  const netLiqStatus = statusOf(netLiquidity);
  const sp500Status = statusOf(sp500);
  const fedStatus = statusOf(fedAssets);
  const tgaStatus = statusOf(tga);
  const rrpStatus = statusOf(rrp);
  const hyStatus = statusOf(hySpread);
  const stressStatus = statusOf(stress);

  if (netLiquidity.error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="The plumbing data could not be loaded" onRetry={netLiquidity.refetch} />
      </div>
    );
  }

  // Let the reading reflect what the past year actually shows rather than
  // asserting the tide narrative against a weak correlation.
  const overlayReading =
    correlation52w == null
      ? "Equities have tended to follow the liquidity tide; the gap between the lines is the tell."
      : Math.abs(correlation52w) >= 0.3
        ? `Equities have been following the liquidity tide: weekly changes ran a ${signedTwo(correlation52w)} correlation over the past year.`
        : `The tide matters over quarters, not weeks: weekly changes ran only a ${signedTwo(correlation52w)} correlation over the past year. Watch the levels, not the wiggles.`;

  const components: {
    key: string;
    title: string;
    source: string;
    color: string;
    status: SectionStatus;
    data: DataPoint[];
  }[] = [
    {
      key: "fed",
      title: "Fed total assets",
      source: "FRED, WALCL. Weekly.",
      color: "var(--chart-1)",
      status: fedStatus,
      data: scaleSeries(fedAssets.data, M),
    },
    {
      key: "tga",
      title: "Treasury General Account",
      source: "FRED, WTREGEN. Weekly.",
      color: "var(--chart-3)",
      status: tgaStatus,
      data: scaleSeries(tga.data, M),
    },
    {
      key: "rrp",
      title: "Overnight reverse repo",
      source: "FRED, RRPONTSYD. Daily.",
      color: "var(--chart-4)",
      status: rrpStatus,
      data: scaleSeries(rrp.data, B),
    },
  ];

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          The Plumbing
        </span>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          Where the dollars actually move.
        </h1>
        {netLiqStatus === "pending" ? (
          <div className="mt-5 max-w-[70ch] animate-pulse space-y-2" aria-label="Loading the lead">
            <div className="h-5 w-full rounded bg-muted" />
            <div className="h-5 w-2/3 rounded bg-muted" />
          </div>
        ) : (
          <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
            {lead ?? "Net liquidity data is unavailable right now."}
          </p>
        )}
      </section>

      {/* Net liquidity vs S&P 500 */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Net liquidity vs S&P 500"
        reading={overlayReading}
        source="Net liquidity: Fed total assets − TGA − RRP, via FRED. Weekly. S&P 500: Yahoo Finance."
        control={<RangeTabs value={range} onChange={setRange} ranges={["1y", "2y", "5y", "10y", "all"]} />}
      >
        {netLiqStatus === "pending" || sp500.isLoading ? (
          <SectionSkeleton height={360} />
        ) : sp500Status !== "ready" ? (
          <div className="space-y-3">
            <LiquidityChart
              title="Net liquidity"
              data={netLiqDisplay}
              color="var(--chart-2)"
              height={360}
              valueFormatter={(v) => compactDollars(v)}
            />
            <MonoNote>S&amp;P 500 overlay unavailable in this export; showing net liquidity alone.</MonoNote>
          </div>
        ) : (
          <NetLiquidityRiskChart data={mergedDisplay} height={360} />
        )}
      </ChartSection>

      {/* Components of net liquidity */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">The components of net liquidity</h2>
        <div className="mt-4 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {components.map((c) => (
            <ChartSection key={c.key} title={c.title} source={c.source}>
              {c.status === "pending" ? (
                <SectionSkeleton height={200} />
              ) : c.status === "error" ? (
                <MonoNote>Series unavailable in this export.</MonoNote>
              ) : (
                <LiquidityChart
                  title={c.title}
                  data={c.data}
                  color={c.color}
                  height={200}
                  valueFormatter={(v) => compactDollars(v)}
                />
              )}
            </ChartSection>
          ))}
        </div>
        <p className="mt-6 font-mono text-[0.6875rem] text-muted-foreground/80">
          Net liquidity = Fed assets − TGA − RRP.
        </p>
      </section>

      {/* Credit spreads + funding stress */}
      <div className="rule mt-10" />
      <div className="mt-8 grid gap-10 lg:grid-cols-12">
        <ChartSection
          className="lg:col-span-7"
          title="Credit spreads"
          reading={spreadsReading(latestHyBp, latestIgBp)}
          source="ICE BofA US high-yield and investment-grade option-adjusted spreads, via FRED. Daily, in basis points."
        >
          {hyStatus === "pending" ? (
            <SectionSkeleton height={280} />
          ) : hyStatus === "error" ? (
            <MonoNote>Credit-spread series unavailable in this export.</MonoNote>
          ) : (
            <MultiLineChart
              data={spreadsData}
              series={[
                { key: "highYield", label: "High yield", color: "var(--pillar-stress)" },
                { key: "investmentGrade", label: "Investment grade", color: "var(--chart-1)" },
              ]}
              height={280}
              valueFormatter={(v) => `${Math.round(v)}bp`}
            />
          )}
        </ChartSection>
        <ChartSection
          className="lg:col-span-5"
          title="Funding stress"
          reading={stressReading(latestOf(stress.data))}
          source="Composite z-score of credit spreads and funding rates. Zero is the recent norm; higher is tighter."
        >
          {stressStatus === "pending" ? (
            <SectionSkeleton height={280} />
          ) : stressStatus === "error" ? (
            <MonoNote>Funding-stress index unavailable in this export.</MonoNote>
          ) : (
            <LiquidityChart
              title="Funding stress"
              data={stress.data}
              color="var(--chart-2)"
              height={280}
              valueFormatter={(v) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}σ`}
              referenceLine={0}
              referenceLabel="0"
            />
          )}
        </ChartSection>
      </div>

      {/* Central banks */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Central-bank balance sheets"
        reading="Each balance sheet indexed to 100 at the start of the range, local currency; divergence between the lines is policy divergence."
        source="Fed (USD), ECB (EUR), BoJ (JPY) total assets, via FRED. Indexed to 100 at range start."
      >
        {fedStatus === "pending" ? (
          <SectionSkeleton height={300} />
        ) : fedStatus === "error" || centralBankData.length === 0 ? (
          <MonoNote>Central-bank balance-sheet series unavailable in this export.</MonoNote>
        ) : (
          <div className="space-y-3">
            <MultiLineChart
              data={centralBankData}
              series={centralBankSeries}
              height={300}
              normalized
              valueFormatter={(v) => v.toFixed(1)}
            />
            {(!ecbReady || !bojReady) && (
              <MonoNote>
                {[!ecbReady ? "ECB" : null, !bojReady ? "BoJ" : null]
                  .filter(Boolean)
                  .join(" and ")}{" "}
                balance-sheet data is missing from this export.
              </MonoNote>
            )}
          </div>
        )}
      </ChartSection>
    </div>
  );
}
