"use client";

import { useMemo } from "react";
import { useFlowsData } from "@/hooks/use-flows-data";
import { useRegimeHistory } from "@/hooks/use-regime-history";
import { ChartSection } from "@/components/chart-section";
import { RatioChart } from "@/components/ratio-chart";
import { Sparkline } from "@/components/sparkline";
import { DataLoadError } from "@/components/data-load-error";
import { formatShortDate, getFreshnessStatus } from "@/lib/data-status";
import {
  flowsHeadline,
  flowsLeadSentence,
  flowsWatchSentence,
  rankedByFlow,
  ratioReading,
  signedNum,
  signedPct,
  signedSigma,
} from "@/lib/flows-brief";
import type { FlowDestination } from "@/lib/api";

// ---------------------------------------------------------------------------
// Scoreboard
// ---------------------------------------------------------------------------

function flowTone(z: number | null): string {
  if (z == null || Math.abs(z) < 1) return "";
  return z > 0 ? "text-positive" : "text-negative";
}

function isRecent(date: string): boolean {
  const tone = getFreshnessStatus(date).tone;
  return tone === "current" || tone === "recent";
}

function ScoreboardRow({ dest }: { dest: FlowDestination }) {
  return (
    <tr className="border-b border-border">
      <td className="py-3 pr-3 align-middle">
        <span className="text-sm font-medium">{dest.name}</span>
        <span className="block text-[0.6875rem] leading-4 text-muted-foreground">
          {dest.group}
        </span>
      </td>
      <td className="py-3 pl-5 text-right align-middle font-mono text-sm tabular-nums">
        {signedPct(dest.ret_4w)}
      </td>
      <td className="py-3 pl-5 text-right align-middle font-mono text-sm tabular-nums">
        {signedPct(dest.ret_13w)}
      </td>
      <td className="py-3 pl-5 text-right align-middle font-mono text-sm tabular-nums">
        {signedPct(dest.ret_26w)}
      </td>
      <td
        className={`py-3 pl-5 text-right align-middle font-mono text-sm tabular-nums ${flowTone(dest.flow_z)}`}
      >
        {signedSigma(dest.flow_z)}
      </td>
      <td className="py-3 pl-5 text-right align-middle font-mono text-sm tabular-nums text-muted-foreground">
        {signedNum(dest.glci_corr_52w)}
      </td>
      <td className="py-3 pl-6 text-right align-middle">
        <Sparkline
          values={dest.spark.map((d) => d.value)}
          width={104}
          height={22}
          stroke="var(--chart-3)"
        />
      </td>
    </tr>
  );
}

function Scoreboard({ destinations }: { destinations: FlowDestination[] }) {
  const head =
    "border-b border-border pb-2 pl-5 text-right font-sans text-[0.6875rem] font-medium text-muted-foreground";
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse">
        <thead>
          <tr>
            <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Asset
            </th>
            <th className={head}>4w</th>
            <th className={head}>13w</th>
            <th className={head}>26w</th>
            <th className={head}>13w z-score</th>
            <th className={head}>GLCI corr</th>
            <th className={`${head} pl-6`}>1y</th>
          </tr>
        </thead>
        <tbody>
          {destinations.map((dest) => (
            <ScoreboardRow key={dest.id} dest={dest} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function FlowsSkeleton() {
  return (
    <div className="animate-pulse space-y-6 pt-10 sm:pt-14" aria-label="Loading price leadership">
      <div className="h-4 w-56 rounded bg-muted" />
      <div className="h-12 w-3/4 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-5 w-full max-w-2xl rounded bg-muted" />
        <div className="h-5 w-2/3 max-w-xl rounded bg-muted" />
      </div>
      <div className="h-72 w-full rounded bg-muted" />
      <div className="h-64 w-full rounded bg-muted" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function FlowsPage() {
  const flows = useFlowsData();
  const history = useRegimeHistory();

  const currentDestinations = useMemo(
    () => flows.data?.destinations.filter((destination) => isRecent(destination.last_date)) ?? [],
    [flows.data]
  );
  const ranked = useMemo(
    () => rankedByFlow(currentDestinations),
    [currentDestinations]
  );

  if (flows.error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="Price leadership could not be loaded" onRetry={flows.refetch} />
      </div>
    );
  }

  if (flows.isLoading || !flows.data) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
        <FlowsSkeleton />
      </div>
    );
  }

  const data = flows.data;
  const freshness = getFreshnessStatus(data.as_of);
  const pageIsCurrent = freshness.tone === "current" || freshness.tone === "recent";
  const lead = pageIsCurrent
    ? flowsLeadSentence(ranked, data.flow_window_weeks)
    : null;
  const headline = !pageIsCurrent
    ? "Price leadership is too old for a current read."
    : ranked.length > 0
      ? flowsHeadline(ranked)
      : currentDestinations.length > 0
        ? "More price history is needed for a leadership z-score."
        : "No fresh asset prices are available for a current read.";
  const watch = pageIsCurrent
    ? flowsWatchSentence(ranked) ?? "Not enough fresh price history is available for a momentum watch."
    : `Price-leadership data through ${formatShortDate(data.as_of)} is more than one week old, so no current momentum watch is shown.`;
  const pairText = data.pair ? ratioReading(data.pair) : null;
  const omittedDestinations = data.destinations.length - currentDestinations.length;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Price Leadership · Data through {formatShortDate(data.as_of)}
        </span>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          {headline}
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          Each asset&apos;s trailing {data.flow_window_weeks}-week return is compared with its own
          three-year history. That puts volatile and stable assets on the same z-score scale. {lead}
        </p>
      </section>

      {/* Scoreboard */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">The scoreboard</h2>
        <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
          Strongest price leadership first. The z-score compares each asset with itself, not with
          the return or volatility of another asset.
        </p>
        {ranked.length > 0 ? (
          <div className="mt-5">
            <Scoreboard destinations={ranked} />
          </div>
        ) : (
          <p className="mt-5 font-serif text-[0.9375rem] italic text-muted-foreground">
            {currentDestinations.length > 0
              ? "Fresh prices are available, but the z-score needs more history."
              : "No asset has a price observation from the past week."}
          </p>
        )}
        <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
          Weekly closes · 13w z-score compares the {data.flow_window_weeks}-week return with the
          asset&apos;s own trailing {data.flow_history_weeks}-week history, colored beyond ±1σ · GLCI
          corr is the {data.glci_corr_window_weeks}-week correlation of weekly returns with weekly
          index changes
        </p>
        {omittedDestinations > 0 && (
          <p className="mt-2 font-mono text-[0.6875rem] text-negative">
            {omittedDestinations} stale {omittedDestinations === 1 ? "asset is" : "assets are"}
            {" "}omitted from the ranking.
          </p>
        )}
      </section>

      {/* Crypto vs the AI trade */}
      {data.pair && data.pair.ratio.length > 0 && (
        <>
          <div className="rule mt-10" />
          <ChartSection
            className="mt-8"
            title="Crypto vs the AI trade"
            reading={pairText ?? undefined}
            source="Weekly ratio of bitcoin to the semiconductor ETF (SMH), indexed to 100 three years ago. Shaded bands mark the liquidity regime in force."
          >
            <RatioChart
              data={data.pair.ratio}
              periods={history.data?.periods}
              valueLabel="BTC / SMH"
              baseline={100}
              height={300}
            />
          </ChartSection>
          {data.pair.spread_13w != null && (
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              Over the past {data.flow_window_weeks} weeks bitcoin has{" "}
              {data.pair.spread_13w >= 0 ? "outrun" : "trailed"} the semiconductor trade by{" "}
              {Math.abs(data.pair.spread_13w * 100).toFixed(1)} percentage points.
            </p>
          )}
        </>
      )}

      {/* Directional watch */}
      {watch && (
        <>
          <div className="rule mt-10" />
          <section className="mt-8">
            <h2 className="text-sm font-semibold tracking-tight">What to watch next</h2>
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              {watch}
            </p>
            <p className="mt-2 max-w-[70ch] font-serif text-sm leading-relaxed text-muted-foreground">
              This is a momentum check, not a return forecast. Price leadership can confirm a
              broader regime view, but it does not establish that strength will continue.
            </p>
          </section>
        </>
      )}

      {/* Method note */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">How to read this</h2>
        <div className="mt-4 max-w-[70ch] space-y-4 font-serif text-[1.0625rem] leading-relaxed">
          <p>
            This is a price-leadership gauge, not fund-flow accounting. Flow-of-funds data arrives
            quarterly and with a long lag. The ranking shows which prices are moving unusually
            fast relative to their own history. It does not show measured capital moving between
            assets.
          </p>
          <p>
            Each asset is normalized against itself: bitcoin uses bitcoin&apos;s history, not the
            S&amp;P 500&apos;s. Consecutive {data.flow_window_weeks}-week windows overlap, so the
            score moves slowly and a reading beyond ±2σ is rare. Use the rank and broad z-score
            band; do not overread one decimal place.
          </p>
        </div>
      </section>
    </div>
  );
}
