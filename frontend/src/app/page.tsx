"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useGLCIData, useIndexData, useSeriesData } from "@/hooks/use-series-data";
import { useRegimeHistory } from "@/hooks/use-regime-history";
import { useBacktestData } from "@/hooks/use-backtest-data";
import { useFlowsData } from "@/hooks/use-flows-data";
import { GlciChart } from "@/components/glci-chart";
import { ChartSection } from "@/components/chart-section";
import { RangeTabs } from "@/components/range-tabs";
import { RegimeStamp } from "@/components/regime-stamp";
import { Sparkline } from "@/components/sparkline";
import { DataLoadError } from "@/components/data-load-error";
import { getDateRange, type TimeRange } from "@/lib/utils";
import { formatShortDate, getFreshnessStatus } from "@/lib/data-status";
import {
  attributionSentence,
  buildChangeItems,
  compactDollars,
  currentRegimeStanding,
  ordinal,
  playbookSentence,
  standingSentence,
  verdictHeadline,
  type ChangeItem,
  type ChangeSpec,
} from "@/lib/brief";
import { flowsHeadline, flowsTeaserSentence } from "@/lib/flows-brief";
import type { DataPoint } from "@/lib/api";

const VITALS_RANGE = getDateRange("6m");

function latestOf(data: DataPoint[]): number | null {
  return data.length ? data[data.length - 1].value : null;
}

function deltaOverDays(data: DataPoint[], days: number): number | null {
  if (data.length < 2) return null;
  const latest = data[data.length - 1];
  const cutoff = new Date(latest.date);
  cutoff.setDate(cutoff.getDate() - days);
  const target = cutoff.toISOString().slice(0, 10);
  for (let i = data.length - 1; i >= 0; i--) {
    if (data[i].date <= target) return latest.value - data[i].value;
  }
  return null;
}

const DIRECTION_GLYPH: Record<ChangeItem["direction"], { glyph: string; className: string }> = {
  supportive: { glyph: "▲", className: "text-positive" },
  restrictive: { glyph: "▼", className: "text-negative" },
  flat: { glyph: "—", className: "text-muted-foreground" },
};

interface VitalProps {
  label: string;
  value: string | null;
  delta: string | null;
  deltaGood: boolean | null;
  spark: number[];
}

function Vital({ label, value, delta, deltaGood, spark }: VitalProps) {
  return (
    <div className="flex flex-col gap-1.5 border-t border-border pt-3">
      <span className="text-xs font-medium tracking-wide text-muted-foreground">{label}</span>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-lg tabular-nums">{value ?? "–"}</span>
        {delta && (
          <span
            className={`font-mono text-xs tabular-nums ${
              deltaGood == null ? "text-muted-foreground" : deltaGood ? "text-positive" : "text-negative"
            }`}
          >
            {delta}
          </span>
        )}
      </div>
      {spark.length > 1 && <Sparkline values={spark} width={120} height={22} stroke="var(--chart-3)" />}
    </div>
  );
}

function BriefSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-label="Loading the brief">
      <div className="h-4 w-48 rounded bg-muted" />
      <div className="h-12 w-3/4 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-5 w-full max-w-2xl rounded bg-muted" />
        <div className="h-5 w-2/3 max-w-xl rounded bg-muted" />
      </div>
      <div className="h-72 w-full rounded bg-muted" />
    </div>
  );
}

export default function TodayPage() {
  const [chartRange, setChartRange] = useState<TimeRange>("2y");
  const chartDates = useMemo(() => getDateRange(chartRange), [chartRange]);

  const glci = useGLCIData({ start: chartDates.start, end: chartDates.end });
  const history = useRegimeHistory();
  const backtest = useBacktestData();
  const flows = useFlowsData();

  const netLiquidity = useIndexData("fed_net_liquidity", VITALS_RANGE);
  const rrp = useSeriesData("fed_reverse_repo", VITALS_RANGE);
  const tga = useSeriesData("fed_treasury_general_account", VITALS_RANGE);
  const hySpread = useSeriesData("ice_bofa_us_high_yield_spread", VITALS_RANGE);
  const sofr = useSeriesData("sofr", VITALS_RANGE);
  const stress = useIndexData("usd_funding_stress", VITALS_RANGE);

  const standing = useMemo(
    () =>
      glci.data
        ? currentRegimeStanding(history.data, glci.data.regime, glci.data.date)
        : null,
    [history.data, glci.data]
  );

  const changes = useMemo(() => {
    const specs: ChangeSpec[] = [
      { label: "Net liquidity", data: netLiquidity.data, scale: 1e6, unit: "usd", goodWhen: "up", flatBelow: 2e9 },
      { label: "The reverse-repo facility", data: rrp.data, scale: 1e9, unit: "usd", goodWhen: "down", flatBelow: 2e9 },
      { label: "The Treasury General Account", data: tga.data, scale: 1e6, unit: "usd", goodWhen: "down", flatBelow: 2e9 },
      { label: "High-yield spreads", data: hySpread.data, scale: 100, unit: "bps", goodWhen: "down", flatBelow: 4 },
      { label: "SOFR", data: sofr.data, unit: "pct", goodWhen: "down", flatBelow: 0.02 },
      { label: "The funding-stress index", data: stress.data, unit: "index", goodWhen: "down", flatBelow: 0.15 },
    ];
    return buildChangeItems(specs);
  }, [netLiquidity.data, rrp.data, tga.data, hySpread.data, sofr.data, stress.data]);

  const playbook = useMemo(
    () => (glci.data ? playbookSentence(backtest.data, glci.data.regime) : null),
    [backtest.data, glci.data]
  );
  const playbookGold = useMemo(
    () =>
      glci.data
        ? playbookSentence(backtest.data, glci.data.regime, "gold_price", "gold")
        : null,
    [backtest.data, glci.data]
  );

  const flowsTeaser = useMemo(
    () => (flows.data ? flowsTeaserSentence(flows.data.destinations) : null),
    [flows.data]
  );

  const freshness = glci.data ? getFreshnessStatus(glci.data.date) : null;
  const isStale = freshness?.tone === "stale" || freshness?.tone === "old";

  if (glci.error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="The brief could not be loaded" onRetry={glci.refetch} />
      </div>
    );
  }

  if (glci.isLoading || !glci.data || !standing) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <BriefSkeleton />
      </div>
    );
  }

  const g = glci.data;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* The verdict */}
      <section className="pt-10 sm:pt-14">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
            The Brief · Data through {formatShortDate(g.date)}
          </span>
          <RegimeStamp regime={g.regime} detail={`${ordinal(standing.weeks)} week`} />
        </div>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          {verdictHeadline(g.regime, g.momentum)}
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          {standingSentence(g, standing)} {attributionSentence(g.pillars)}
        </p>
        {isStale && (
          <p className="mt-3 font-mono text-xs text-negative">
            Note: the latest data point is {formatShortDate(g.date)}; the pipeline may be behind.
          </p>
        )}
      </section>

      {/* The index */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Global Liquidity & Credit Index"
        reading="Shaded bands mark the regime in force at the time; the index is scaled to mean 100, one band per 10 points."
        source="Composite of liquidity (40%), credit (35%) and inverted funding-stress (25%) factors. Weekly."
        control={<RangeTabs value={chartRange} onChange={setChartRange} ranges={["1y", "2y", "5y", "10y", "all"]} />}
      >
        <GlciChart data={g.data} periods={history.data?.periods} height={320} />
      </ChartSection>

      {/* What changed + playbook */}
      <div className="rule mt-10" />
      <div className="mt-8 grid gap-10 lg:grid-cols-12">
        <section className="lg:col-span-7">
          <h2 className="text-sm font-semibold tracking-tight">What changed</h2>
          {changes.length === 0 ? (
            <p className="mt-3 font-serif text-[0.9375rem] italic text-muted-foreground">
              Not enough recent data to summarize the week.
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {changes.map((item) => {
                const mark = DIRECTION_GLYPH[item.direction];
                return (
                  <li key={item.label} className="flex items-baseline gap-3">
                    <span aria-hidden="true" className={`font-mono text-[0.625rem] ${mark.className}`}>
                      {mark.glyph}
                    </span>
                    <span className="font-serif text-[1.0625rem] leading-snug">{item.text}</span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-4 font-mono text-[0.6875rem] text-muted-foreground/80">
            ▲ supportive of liquidity · ▼ restrictive · one-week moves
          </p>
        </section>

        <aside className="lg:col-span-5">
          <h2 className="text-sm font-semibold tracking-tight">
            What {standing.regime} regimes have meant
          </h2>
          {playbook ? (
            <div className="mt-4 space-y-4">
              <p className="font-serif text-[1.0625rem] leading-relaxed">{playbook.text}</p>
              {playbookGold && (
                <p className="font-serif text-[1.0625rem] leading-relaxed text-muted-foreground">
                  {playbookGold.text}
                </p>
              )}
              <Link
                href="/playbook"
                className="inline-block font-mono text-xs text-primary underline-offset-4 hover:underline"
              >
                Full playbook, all assets and horizons →
              </Link>
            </div>
          ) : (
            <p className="mt-4 font-serif text-[0.9375rem] italic text-muted-foreground">
              Backtest results are unavailable right now.
            </p>
          )}
        </aside>
      </div>

      {/* Where the marginal dollar is going */}
      {flows.data && flowsTeaser && (
        <>
          <div className="rule mt-10" />
          <section className="mt-8">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold tracking-tight">
                Where the marginal dollar is going
              </h2>
              <Link
                href="/flows"
                className="font-mono text-xs text-primary underline-offset-4 hover:underline"
              >
                The flows →
              </Link>
            </div>
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              {flowsHeadline(flows.data.destinations)} {flowsTeaser}
            </p>
          </section>
        </>
      )}

      {/* Vitals */}
      <div className="mt-12" />
      <section aria-label="Plumbing vitals">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold tracking-tight">The plumbing, at a glance</h2>
          <Link
            href="/plumbing"
            className="font-mono text-xs text-primary underline-offset-4 hover:underline"
          >
            Detail →
          </Link>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          <Vital
            label="Net liquidity"
            value={latestOf(netLiquidity.data) != null ? compactDollars(latestOf(netLiquidity.data)! * 1e6) : null}
            delta={(() => { const d = deltaOverDays(netLiquidity.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${compactDollars(Math.abs(d) * 1e6)}` : null; })()}
            deltaGood={(() => { const d = deltaOverDays(netLiquidity.data, 7); return d != null ? d >= 0 : null; })()}
            spark={netLiquidity.data.map((d) => d.value)}
          />
          <Vital
            label="Reverse repo"
            value={latestOf(rrp.data) != null ? compactDollars(latestOf(rrp.data)! * 1e9) : null}
            delta={(() => { const d = deltaOverDays(rrp.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${compactDollars(Math.abs(d) * 1e9)}` : null; })()}
            deltaGood={(() => { const d = deltaOverDays(rrp.data, 7); return d != null ? d <= 0 : null; })()}
            spark={rrp.data.map((d) => d.value)}
          />
          <Vital
            label="Treasury account"
            value={latestOf(tga.data) != null ? compactDollars(latestOf(tga.data)! * 1e6) : null}
            delta={(() => { const d = deltaOverDays(tga.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${compactDollars(Math.abs(d) * 1e6)}` : null; })()}
            deltaGood={(() => { const d = deltaOverDays(tga.data, 7); return d != null ? d <= 0 : null; })()}
            spark={tga.data.map((d) => d.value)}
          />
          <Vital
            label="HY spread"
            value={latestOf(hySpread.data) != null ? `${Math.round(latestOf(hySpread.data)! * 100)}bp` : null}
            delta={(() => { const d = deltaOverDays(hySpread.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${Math.abs(Math.round(d * 100))}bp` : null; })()}
            deltaGood={(() => { const d = deltaOverDays(hySpread.data, 7); return d != null ? d <= 0 : null; })()}
            spark={hySpread.data.map((d) => d.value)}
          />
          <Vital
            label="SOFR"
            value={latestOf(sofr.data) != null ? `${latestOf(sofr.data)!.toFixed(2)}%` : null}
            delta={(() => { const d = deltaOverDays(sofr.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(2)}pp` : null; })()}
            deltaGood={null}
            spark={sofr.data.map((d) => d.value)}
          />
          <Vital
            label="Funding stress"
            value={(() => { const v = latestOf(stress.data); return v != null ? `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}σ` : null; })()}
            delta={(() => { const d = deltaOverDays(stress.data, 7); return d != null ? `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(2)}` : null; })()}
            deltaGood={(() => { const d = deltaOverDays(stress.data, 7); return d != null ? d <= 0 : null; })()}
            spark={stress.data.map((d) => d.value)}
          />
        </div>
      </section>
    </div>
  );
}
