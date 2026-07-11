"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useGLCIData, useIndexData, useSeriesData } from "@/hooks/use-series-data";
import { useRegimeHistory } from "@/hooks/use-regime-history";
import { useBacktestData } from "@/hooks/use-backtest-data";
import { useFlowsData } from "@/hooks/use-flows-data";
import { useGLCITrust } from "@/hooks/use-glci-trust";
import { GlciChart } from "@/components/glci-chart";
import { ChartSection } from "@/components/chart-section";
import { RangeTabs } from "@/components/range-tabs";
import { RegimeStamp } from "@/components/regime-stamp";
import { Sparkline } from "@/components/sparkline";
import { DataLoadError } from "@/components/data-load-error";
import { DirectionalOutlookView } from "@/components/directional-outlook";
import { getDateRange, type TimeRange } from "@/lib/utils";
import { formatShortDate, getFreshnessStatus } from "@/lib/data-status";
import {
  attributionSentence,
  buildChangeItems,
  compactDollars,
  currentRegimeStanding,
  invalidationSentence,
  ordinal,
  standingSentence,
  transitionView,
  verdictHeadline,
  type ChangeItem,
  type ChangeSpec,
} from "@/lib/brief";
import { flowsTeaserSentence } from "@/lib/flows-brief";
import { buildDirectionalOutlook } from "@/lib/outlook";
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

const TRANSITION_TONE = {
  improving: "text-positive",
  weakening: "text-negative",
  stable: "text-muted-foreground",
} as const;

function componentList(items: string[]): string {
  const shown = items.slice(0, 3).map((item) => item.replaceAll("_", " "));
  const remainder = items.length - shown.length;
  return remainder > 0 ? `${shown.join(", ")} and ${remainder} more` : shown.join(", ");
}

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
  const trust = useGLCITrust();

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
      { label: "The credit-stress index", data: stress.data, unit: "index", goodWhen: "down", flatBelow: 0.15 },
    ];
    return buildChangeItems(specs);
  }, [netLiquidity.data, rrp.data, tga.data, hySpread.data, sofr.data, stress.data]);

  const flowsTeaser = useMemo(
    () => {
      if (!flows.data) return null;
      const current = flows.data.destinations.filter((destination) => {
        const tone = getFreshnessStatus(destination.last_date).tone;
        return tone === "current" || tone === "recent";
      });
      return flowsTeaserSentence(current);
    },
    [flows.data]
  );

  const outlook = useMemo(
    () =>
      glci.data
        ? buildDirectionalOutlook(
            backtest.data,
            flows.data,
            glci.data.regime,
            glci.data.date
          )
        : null,
    [backtest.data, flows.data, glci.data]
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
  const transition = transitionView(g.momentum);
  const topChanges = changes.slice(0, 4);
  const dataQuality = trust.data?.data_quality;
  const missingComponents = dataQuality?.missing_components ?? [];
  const staleComponents = dataQuality?.stale_components ?? [];
  const excludedComponents = dataQuality?.excluded_components ?? [];
  const failedPillars = dataQuality?.failed_pillars ?? [];
  const integrityIssues = [
    failedPillars.length > 0 ? `Failed pillars: ${componentList(failedPillars)}.` : null,
    staleComponents.length > 0 ? `Stale: ${componentList(staleComponents)}.` : null,
    missingComponents.length > 0 ? `Missing: ${componentList(missingComponents)}.` : null,
    excludedComponents.length > 0 ? `Excluded from fit: ${componentList(excludedComponents)}.` : null,
  ].filter((issue): issue is string => issue !== null);
  const trustFrequency = trust.data?.frequency || "Weekly";
  const snapshotCount = trust.data?.snapshots.count ?? 0;
  const reconstructedHistory = trust.data?.point_in_time !== true;

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

      {/* Decision frame */}
      <div className="rule mt-10" />
      <section className="mt-8" aria-labelledby="decision-frame-title">
        <h2 id="decision-frame-title" className="sr-only">Decision frame</h2>
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-sm font-semibold tracking-tight">Current transition</span>
              <span
                className={`font-mono text-xs uppercase tracking-[0.14em] ${TRANSITION_TONE[transition.state]}`}
              >
                {transition.state}
              </span>
            </div>
            <p className="mt-2 font-serif text-[1.0625rem] leading-relaxed text-muted-foreground">
              {transition.detail}
            </p>

            <h3 className="mt-7 text-sm font-semibold tracking-tight">What changed</h3>
            {topChanges.length === 0 ? (
              <p className="mt-3 font-serif text-[0.9375rem] italic text-muted-foreground">
                Not enough recent data to summarize the week.
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {topChanges.map((item) => {
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
          </div>

          <aside className="border-t border-border pt-7 lg:col-span-5 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
            <h3 className="text-sm font-semibold tracking-tight">What would change this view</h3>
            <p className="mt-3 font-serif text-[1.0625rem] leading-relaxed">
              {invalidationSentence(g)}
            </p>
          </aside>
        </div>

        <div className="mt-8 border-y border-border py-6" aria-label="Directional outlook">
          <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-2">
            <h3 className="text-sm font-semibold tracking-tight">What the data favors now</h3>
            <Link
              href="/playbook"
              className="font-mono text-xs text-primary underline-offset-4 hover:underline"
            >
              Full playbook →
            </Link>
          </div>
          <div className="mt-4">
            {outlook ? (
              <DirectionalOutlookView outlook={outlook} compact />
            ) : (
              <p className="font-serif text-[0.9375rem] italic text-muted-foreground">
                Historical forward-return results are unavailable right now.
              </p>
            )}
          </div>
        </div>

        <div className="mt-8 border-b border-border pb-4" aria-label="Signal integrity">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
            <span className="text-xs font-semibold uppercase tracking-[0.12em]">Signal integrity</span>
            {dataQuality && dataQuality.total_components > 0 ? (
              <span className="font-mono text-xs text-muted-foreground">
                Coverage {dataQuality.loaded_components}/{dataQuality.total_components}
              </span>
            ) : (
              <span className="font-mono text-xs text-muted-foreground">
                Component coverage unavailable
              </span>
            )}
            <span className="font-mono text-xs text-muted-foreground">{trustFrequency} cadence</span>
            {snapshotCount > 0 && (
              <span className="font-mono text-xs text-muted-foreground">
                {snapshotCount} recorded {snapshotCount === 1 ? "vintage" : "vintages"}
              </span>
            )}
          </div>
          {integrityIssues.length > 0 && (
            <p className="mt-2 font-mono text-xs text-negative">
              {integrityIssues.join(" ")}
            </p>
          )}
          {reconstructedHistory && (
            <p className="mt-2 max-w-[90ch] font-serif text-sm leading-relaxed">
              <span className="font-medium">Reconstructed history.</span>{" "}
              <span className="text-muted-foreground">
                Historical readings use the current data vintage and are not point-in-time. Source
                revisions and factor re-estimation can change past values and regime labels.
              </span>
            </p>
          )}
        </div>
      </section>

      {/* The index */}
      <div className="rule mt-10" />
      <ChartSection
        className="mt-8"
        title="Global Liquidity & Credit Index"
        reading="Shaded bands mark the regime in force in the reconstructed series; the index is scaled to mean 100, one band per 10 points."
        source="Composite of liquidity (40%), credit (35%) and inverted funding-stress (25%) factors. Weekly."
        control={<RangeTabs value={chartRange} onChange={setChartRange} ranges={["1y", "2y", "5y", "10y", "all"]} />}
      >
        <GlciChart data={g.data} periods={history.data?.periods} height={320} />
      </ChartSection>

      {/* Price leadership */}
      {flows.data && flowsTeaser && (
        <>
          <div className="rule mt-10" />
          <section className="mt-8">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold tracking-tight">
                Price leadership over 13 weeks
              </h2>
              <Link
                href="/flows"
                className="font-mono text-xs text-primary underline-offset-4 hover:underline"
              >
                Price leadership →
              </Link>
            </div>
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              {flowsTeaser}
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
            label="Credit stress"
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
