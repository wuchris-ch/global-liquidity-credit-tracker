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
import type {
  FlowDestination,
  SectorFlowConfirmation,
  SectorRotationPhase,
  SectorRotationResponse,
  SectorRotationRow,
} from "@/lib/api";

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
// Sector rotation
// ---------------------------------------------------------------------------

const PHASE_LABELS: Record<SectorRotationPhase, string> = {
  leading: "Leading",
  weakening: "Weakening",
  improving: "Improving",
  lagging: "Lagging",
};

const CONFIRMATION_LABELS: Record<SectorFlowConfirmation, string> = {
  supports: "Supports price phase",
  diverges: "Diverges from price phase",
  neutral: "Neutral issuance",
};

function naturalList(values: string[]): string {
  if (values.length === 0) return "None currently";
  if (values.length === 1) return values[0];
  if (values.length === 2) return values[0] + " and " + values[1];
  return values.slice(0, -1).join(", ") + ", and " + values[values.length - 1];
}

function sectorLabels(ids: string[], sectors: SectorRotationRow[]): string[] {
  const byId = new Map(sectors.map((sector) => [sector.id, sector]));
  return ids
    .map((id) => byId.get(id))
    .filter((sector): sector is SectorRotationRow => sector != null)
    .map((sector) => sector.name + " (" + sector.ticker + ")");
}

function phaseTone(phase: SectorRotationPhase): string {
  if (phase === "leading") return "text-positive";
  if (phase === "lagging") return "text-negative";
  if (phase === "improving") return "text-primary";
  return "text-muted-foreground";
}

function confirmationTone(confirmation: SectorFlowConfirmation): string {
  if (confirmation === "supports") return "text-positive";
  if (confirmation === "diverges") return "text-negative";
  return "text-muted-foreground";
}

function formatUsd(value: number | null): string {
  if (value == null) return "–";
  const sign = value < 0 ? "−" : value > 0 ? "+" : "";
  const absolute = Math.abs(value);
  if (absolute >= 1e9) return sign + "$" + (absolute / 1e9).toFixed(1) + "bn";
  if (absolute >= 1e6) return sign + "$" + (absolute / 1e6).toFixed(0) + "m";
  if (absolute >= 1e3) return sign + "$" + (absolute / 1e3).toFixed(0) + "k";
  return sign + "$" + absolute.toFixed(0);
}

function formatContracts(value: number | null | undefined): string {
  if (value == null) return "Unavailable";
  if (value >= 1e6) return (value / 1e6).toFixed(1) + "m contracts";
  if (value >= 1e3) return (value / 1e3).toFixed(0) + "k contracts";
  return Math.round(value) + " contracts";
}

function formatMultiple(value: number | null | undefined): string {
  return value == null ? "–" : value.toFixed(2) + "×";
}

function SectorOpportunitySummary({ data }: { data: SectorRotationResponse }) {
  const leaders = sectorLabels(data.opportunities.leaders, data.sectors);
  const improving = sectorLabels(data.opportunities.improving, data.sectors);
  const laggards = sectorLabels(data.opportunities.laggards, data.sectors);

  return (
    <div className="mt-6 grid gap-5 sm:grid-cols-3">
      <div className="border-t border-border pt-3">
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.12em] text-muted-foreground">
          Price leaders
        </p>
        <p className="mt-2 font-serif text-[0.9375rem] leading-relaxed">
          {leaders.length > 0
            ? naturalList(leaders) + " rank highest on the price-only score."
            : "No complete leader set is available for this update."}
        </p>
      </div>
      <div className="border-t border-border pt-3">
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.12em] text-muted-foreground">
          Early improvement
        </p>
        <p className="mt-2 font-serif text-[0.9375rem] leading-relaxed">
          {improving.length > 0
            ? naturalList(improving) +
              " still lag SPY over the medium term, but short-term relative momentum has turned up."
            : "No lagging sector currently has positive short-term relative acceleration."}
        </p>
      </div>
      <div className="border-t border-border pt-3">
        <p className="font-mono text-[0.6875rem] uppercase tracking-[0.12em] text-muted-foreground">
          Price laggards
        </p>
        <p className="mt-2 font-serif text-[0.9375rem] leading-relaxed">
          {laggards.length > 0
            ? naturalList(laggards) + " sit at the bottom of the current price ranking."
            : "No complete laggard set is available for this update."}
        </p>
      </div>
    </div>
  );
}

function SectorRotationTable({ sectors }: { sectors: SectorRotationRow[] }) {
  const head =
    "border-b border-border pb-2 pl-4 text-right font-sans text-[0.6875rem] font-medium text-muted-foreground";

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1040px] border-collapse">
        <caption className="sr-only">
          Select Sector SPDR price rotation, net issuance estimates, and OCC cleared options activity
        </caption>
        <thead>
          <tr>
            <th className="border-b border-border pb-2 pr-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Rank
            </th>
            <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Sector
            </th>
            <th className={head + " text-left"}>Phase</th>
            <th className={head}>Price score</th>
            <th className={head}>1m vs SPY</th>
            <th className={head}>3m vs SPY</th>
            <th className={head}>6m vs SPY</th>
            <th className={head}>20d net issuance</th>
            <th className={head}>Issuance z</th>
            <th className={head}>OCC vs avg</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((sector) => (
            <tr key={sector.id} className="border-b border-border">
              <td className="py-3 pr-2 align-middle font-mono text-xs tabular-nums text-muted-foreground">
                {sector.rank}
              </td>
              <td className="py-3 pr-3 align-middle">
                <span className="text-sm font-medium">{sector.name}</span>
                <span className="block font-mono text-[0.6875rem] leading-4 text-muted-foreground">
                  {sector.ticker} · {sector.above_200d ? "above" : "below"} 200d average
                </span>
              </td>
              <td
                className={
                  "py-3 pl-4 align-middle font-mono text-xs " + phaseTone(sector.phase)
                }
              >
                {PHASE_LABELS[sector.phase]}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {sector.price_score == null ? "–" : sector.price_score.toFixed(1)}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {signedPct(sector.excess_21d)}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {signedPct(sector.excess_63d)}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {signedPct(sector.excess_126d)}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {signedPct(sector.fund_flow.flow_20d_pct_aum)}
                <span className="block font-sans text-[0.625rem] leading-4 text-muted-foreground">
                  {formatUsd(sector.fund_flow.flow_20d_usd)}
                </span>
                <span
                  className={
                    "block font-sans text-[0.625rem] leading-4 " +
                    confirmationTone(sector.flow_confirmation)
                  }
                >
                  {CONFIRMATION_LABELS[sector.flow_confirmation]}
                </span>
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {signedSigma(sector.fund_flow.flow_20d_z)}
              </td>
              <td className="py-3 pl-4 text-right align-middle font-mono text-sm tabular-nums">
                {formatMultiple(sector.options_activity?.activity_ratio)}
                <span className="block font-sans text-[0.625rem] leading-4 text-muted-foreground">
                  {formatContracts(sector.options_activity?.total_volume)}
                  {sector.options_activity?.put_call_ratio != null
                    ? " · P/C " + sector.options_activity.put_call_ratio.toFixed(2)
                    : ""}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectorRotationSection({ data }: { data: SectorRotationResponse }) {
  const sectors = [...data.sectors].sort((a, b) => a.rank - b.rank);
  const leaders = sectorLabels(data.opportunities.leaders.slice(0, 2), sectors);
  const laggards = sectorLabels(data.opportunities.laggards.slice(-2), sectors);
  const inflows = sectorLabels(data.opportunities.strongest_inflows, sectors);
  const activeOptions = sectorLabels(data.opportunities.most_active_options, sectors);
  const optionsCoverage =
    data.coverage.options + " of " + data.coverage.expected_sectors;
  const optionsAvailable = data.coverage.options > 0 && activeOptions.length > 0;
  const priceBasis = "Yahoo Finance adjusted closes";

  return (
    <>
      <div className="rule mt-10" />
      <section className="mt-8">
        <span className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted-foreground">
          Select Sector SPDRs · Prices through {formatShortDate(data.price_as_of)}
        </span>
        <h2 className="mt-3 max-w-3xl font-serif text-3xl font-medium leading-tight tracking-tight">
          {leaders.length > 0 && laggards.length > 0
            ? naturalList(leaders) + " lead; " + naturalList(laggards) + " lag."
            : "The sector rotation map"}
        </h2>
        <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed text-muted-foreground">
          The ranking compares all {data.coverage.expected_sectors} Select Sector SPDRs with{" "}
          {data.benchmark}. Its 0 to 100 score combines medium-term relative strength and
          risk-adjusted absolute trend. It is a descriptive price signal, not a tested return
          forecast.
        </p>

        <SectorOpportunitySummary data={data} />

        <div className="mt-7">
          <SectorRotationTable sectors={sectors} />
        </div>
        <p className="mt-3 font-mono text-[0.6875rem] leading-relaxed text-muted-foreground/80">
          Price score: 65% medium-term relative-strength percentile + 35% absolute-trend
          percentile · Relative returns are vs {data.benchmark} · Prices: {priceBasis} · OCC
          activity: weekly daily average / prior-month daily average · Net issuance and OCC
          activity are excluded from the score
        </p>

        <div className="mt-7 grid gap-6 sm:grid-cols-2">
          <div className="border-t border-border pt-4">
            <h3 className="text-sm font-semibold tracking-tight">
              State Street net issuance estimates
            </h3>
            <p className="mt-2 font-serif text-[0.9375rem] leading-relaxed text-muted-foreground">
              Through {formatShortDate(data.fund_flow_as_of)}, the strongest 20-session issuance
              readings were {naturalList(inflows)}. The estimate is NAV multiplied by the
              split-adjusted change in shares outstanding. It measures primary-market net
              issuance, not secondary-market buying, investor intent, or a directional forecast.
              Sponsor histories are current workbooks and may be revised.
            </p>
          </div>
          <div className="border-t border-border pt-4">
            <h3 className="text-sm font-semibold tracking-tight">
              OCC cleared options activity
            </h3>
            <p className="mt-2 font-serif text-[0.9375rem] leading-relaxed text-muted-foreground">
              {optionsAvailable
                ? "Through " +
                  formatShortDate(data.options_as_of) +
                  ", activity was most elevated versus its prior-month daily average in " +
                  naturalList(activeOptions) +
                  ". Coverage is " +
                  optionsCoverage +
                  " sectors."
                : "OCC activity is unavailable for this update; the price and net-issuance evidence remain usable."}{" "}
              OCC cleared volume is non-directional: it does not identify buyer versus seller,
              opening versus closing, or bullish versus bearish intent. Only standard product
              roots are included; adjusted roots are excluded from the aggregate.
            </p>
          </div>
        </div>

        {(!data.coverage.complete_price_universe ||
          !data.coverage.complete_fund_flow_universe ||
          data.coverage.options_status === "partial") && (
          <p className="mt-4 font-mono text-[0.6875rem] leading-relaxed text-negative">
            Partial coverage: price {data.coverage.price}/{data.coverage.expected_sectors}, net
            issuance {data.coverage.fund_flows}/{data.coverage.expected_sectors}, OCC activity{" "}
            {optionsCoverage}.
          </p>
        )}
      </section>
    </>
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

      {/* Sector rotation: optional while the static payload rolls forward */}
      {data.sector_rotation && data.sector_rotation.sectors.length > 0 && (
        <SectorRotationSection data={data.sector_rotation} />
      )}

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
            The cross-asset scoreboard is a price-leadership gauge, not fund-flow accounting. It
            shows which prices are moving unusually fast relative to their own history. {data.sector_rotation
              ? "The sector section separately presents State Street net issuance estimates and OCC cleared activity; neither evidence layer changes a price score."
              : "It does not show measured capital moving between assets."}
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
