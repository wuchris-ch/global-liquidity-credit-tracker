"use client";

import { useMemo } from "react";
import { useFlowsData } from "@/hooks/use-flows-data";
import { useRegimeHistory } from "@/hooks/use-regime-history";
import { ChartSection } from "@/components/chart-section";
import { RatioChart } from "@/components/ratio-chart";
import { Sparkline } from "@/components/sparkline";
import { DataLoadError } from "@/components/data-load-error";
import { formatShortDate } from "@/lib/data-status";
import {
  flowsHeadline,
  flowsLeadSentence,
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
              Destination
            </th>
            <th className={head}>4w</th>
            <th className={head}>13w</th>
            <th className={head}>26w</th>
            <th className={head}>Bid vs norm</th>
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
    <div className="animate-pulse space-y-6 pt-10 sm:pt-14" aria-label="Loading the flows">
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

  const ranked = useMemo(
    () => (flows.data ? rankedByFlow(flows.data.destinations) : []),
    [flows.data]
  );

  if (flows.error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="The flows could not be loaded" onRetry={flows.refetch} />
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
  const lead = flowsLeadSentence(data.destinations, data.flow_window_weeks);
  const pairText = data.pair ? ratioReading(data.pair) : null;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          The Flows · Data through {formatShortDate(data.as_of)}
        </span>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          {flowsHeadline(data.destinations)}
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          Each destination is scored by how unusual its trailing {data.flow_window_weeks}-week
          bid is against its own three-year norm, so a volatile asset has to rally harder to
          rank. {lead}
        </p>
      </section>

      {/* Scoreboard */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">The scoreboard</h2>
        <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
          Strongest bid first. The score compares each asset with itself, so it reads as
          where the marginal dollar is showing up, not which asset returned the most.
        </p>
        <div className="mt-5">
          <Scoreboard destinations={ranked} />
        </div>
        <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
          Weekly closes · bid vs norm is the {data.flow_window_weeks}-week return as a z-score
          against the asset&apos;s own trailing {data.flow_history_weeks}-week history, colored
          beyond ±1σ · GLCI corr is the {data.glci_corr_window_weeks}-week correlation of weekly
          returns with weekly index changes
        </p>
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

      {/* Method note */}
      <div className="rule mt-10" />
      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">How to read this</h2>
        <div className="mt-4 max-w-[70ch] space-y-4 font-serif text-[1.0625rem] leading-relaxed">
          <p>
            This page is a bid gauge, not fund-flow accounting. True flow-of-funds data
            arrives quarterly and with a long lag; daily prices are the cleanest live proxy
            for where the marginal dollar lands. When one destination outruns its own norm
            while another undershoots, the page reads that spread as liquidity choosing
            sides.
          </p>
          <p>
            The score normalizes each asset against itself: bitcoin&apos;s norm is bitcoin&apos;s
            volatility, not the S&amp;P&apos;s. Consecutive {data.flow_window_weeks}-week windows
            overlap, so the score moves slowly by construction and a reading beyond ±2σ is
            rare. Treat the ranking as the signal and any single decimal as noise.
          </p>
        </div>
      </section>
    </div>
  );
}
