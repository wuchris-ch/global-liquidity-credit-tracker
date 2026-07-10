"use client";

import { useEffect, useMemo, useState } from "react";
import { useBacktestData } from "@/hooks/use-backtest-data";
import { useRiskData } from "@/hooks/use-risk-data";
import { RegimeStamp, regimeLabel } from "@/components/regime-stamp";
import { DataLoadError } from "@/components/data-load-error";
import { formatShortDate } from "@/lib/data-status";
import { playbookSentence, signed } from "@/lib/brief";
import api from "@/lib/api";
import type {
  AssetRiskMetrics,
  BacktestAssetResult,
  BacktestBaseRate,
  BacktestHorizon,
  BacktestStats,
  Regime,
} from "@/lib/api";

/**
 * The canonical current regime is the one published by the GLCI endpoint
 * (104-week rolling z-score), which the rest of the app shows. The backtest's
 * own expanding-window classifier can disagree near regime boundaries; that
 * divergence is disclosed, not silently substituted.
 */
function useCanonicalRegime(): { regime: Regime | null; isLoading: boolean } {
  const [regime, setRegime] = useState<Regime | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .getGLCILatest()
      .then((latest) => {
        if (cancelled) return;
        const label = latest.regime_label?.toLowerCase();
        if (label === "loose" || label === "neutral" || label === "tight") {
          setRegime(label);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { regime, isLoading };
}

// ---------------------------------------------------------------------------
// Formatting (true minus signs throughout, mono tabular figures in markup)
// ---------------------------------------------------------------------------

/** "84%" — hit rates as whole numbers. */
function hitPct(v: number | null | undefined): string {
  return v == null ? "–" : `${Math.round(v * 100)}%`;
}

/** "+7.4%" / "−2.1%" — medians as signed percents, one decimal. */
function medPct(v: number | null | undefined): string {
  return v == null ? "–" : `${signed(v * 100, 1)}%`;
}

/** "+9.0pp" — hit-rate edge in percentage points. */
function edgePp(v: number | null | undefined): string {
  return v == null ? "–" : `${signed(v * 100, 1)}pp`;
}

/** "−33.9" — plain number with a true minus sign. */
function num(v: number | null | undefined, decimals = 1): string {
  if (v == null) return "–";
  const fixed = Math.abs(v).toFixed(decimals);
  return v < 0 ? `−${fixed}` : fixed;
}

const REGIME_ORDER: Regime[] = ["loose", "neutral", "tight"];
const PAIRED_BOOTSTRAP_METHOD = "paired_full_calendar_moving_block";

const REGIME_WASH: Record<Regime, string> = {
  loose: "regime-wash-loose",
  neutral: "regime-wash-neutral",
  tight: "regime-wash-tight",
};

const REGIME_TEXT: Record<Regime, string> = {
  loose: "regime-text-loose",
  neutral: "regime-text-neutral",
  tight: "regime-text-tight",
};

// ---------------------------------------------------------------------------
// Statistics helpers
// ---------------------------------------------------------------------------

function cellStats(
  asset: BacktestAssetResult,
  classifier: string,
  regime: Regime,
  horizon: BacktestHorizon
): BacktestStats | null {
  return asset.results?.[classifier]?.[regime]?.[horizon] ?? null;
}

function baseRate(
  asset: BacktestAssetResult,
  horizon: BacktestHorizon
): BacktestBaseRate | null {
  return asset.base_rates?.[horizon] ?? null;
}

/** The edge is distinguishable from zero only when its paired CI excludes zero. */
function edgeSignificant(
  stats: BacktestStats | null,
  pairedInference: boolean
): boolean | null {
  if (
    !pairedInference ||
    !stats ||
    stats.edge == null ||
    stats.ci_edge_low == null ||
    stats.ci_edge_high == null
  ) {
    return null;
  }
  return stats.ci_edge_low > 0 || stats.ci_edge_high < 0;
}

// ---------------------------------------------------------------------------
// Table cells
// ---------------------------------------------------------------------------

/** Hit rate with sample size in small muted type underneath. */
function HitCell({
  stats,
  pairedInference,
}: {
  stats: BacktestStats | null;
  pairedInference: boolean;
}) {
  return (
    <td className="py-3 pl-5 text-right align-top">
      <span className="font-mono text-sm tabular-nums">{hitPct(stats?.hit_rate)}</span>
      <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
        n {stats?.n ?? "–"}
      </span>
      {pairedInference && stats?.ci_hit_rate_low != null && stats?.ci_hit_rate_high != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          subgroup CI {Math.round(stats.ci_hit_rate_low * 100)}–{Math.round(stats.ci_hit_rate_high * 100)}%
        </span>
      )}
    </td>
  );
}

/** Median forward return, signed, one decimal. */
function MedianCell({
  stats,
  className = "",
}: {
  stats: BacktestStats | null;
  className?: string;
}) {
  return (
    <td className={`py-3 pl-5 text-right align-top ${className}`}>
      <span className="font-mono text-sm tabular-nums">{medPct(stats?.median)}</span>
    </td>
  );
}

/**
 * Edge vs base rate: colored only when the paired edge CI excludes zero,
 * otherwise muted with an "n.s." marker. Paired CI shown underneath.
 */
function EdgeCell({
  stats,
  pairedInference,
}: {
  stats: BacktestStats | null;
  pairedInference: boolean;
}) {
  const sig = edgeSignificant(stats, pairedInference);
  const edge = stats?.edge ?? null;
  const tone =
    sig && edge != null && stats?.ci_edge_low != null
      ? stats.ci_edge_low > 0
        ? "text-positive"
        : "text-negative"
      : "text-muted-foreground";
  return (
    <td className="py-3 pl-5 text-right align-top">
      <span className={`font-mono text-sm tabular-nums ${tone}`}>
        {edgePp(edge)}
        {sig === false && (
          <>
            {" "}
            <span className="font-mono text-[0.625rem] text-muted-foreground">n.s.</span>
          </>
        )}
      </span>
      {pairedInference && stats?.ci_edge_low != null && stats?.ci_edge_high != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          paired CI {edgePp(stats.ci_edge_low)} to {edgePp(stats.ci_edge_high)}
        </span>
      )}
      {pairedInference && sig == null && edge != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          CI unavailable
        </span>
      )}
    </td>
  );
}

// ---------------------------------------------------------------------------
// Section 2: forward returns in the current regime (the centerpiece)
// ---------------------------------------------------------------------------

function ForwardReturnsTable({
  assets,
  regime,
  pairedInference,
}: {
  assets: BacktestAssetResult[];
  regime: Regime;
  pairedInference: boolean;
}) {
  const groupHead = "pb-1 pl-5 text-left font-sans text-[0.6875rem] font-semibold uppercase tracking-wider";
  const subHead =
    "border-b border-border pb-2 pl-5 text-right font-sans text-[0.6875rem] font-medium text-muted-foreground";

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] border-collapse">
        <thead>
          <tr>
            <th className="pb-1 text-left" />
            <th colSpan={2} className={`${groupHead} text-muted-foreground`}>
              4 weeks
            </th>
            <th
              colSpan={4}
              className={`${groupHead} ${REGIME_WASH[regime]} ${REGIME_TEXT[regime]} band-inset-x`}
            >
              13 weeks · {regimeLabel(regime)} regime
            </th>
            <th colSpan={2} className={`${groupHead} text-muted-foreground`}>
              26 weeks
            </th>
          </tr>
          <tr>
            <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Asset
            </th>
            <th className={subHead}>Hit</th>
            <th className={subHead}>Median</th>
            <th className={`${subHead} ${REGIME_WASH[regime]} band-inset-l`}>Hit</th>
            <th className={`${subHead} ${REGIME_WASH[regime]}`}>Base</th>
            <th className={`${subHead} ${REGIME_WASH[regime]}`}>Edge</th>
            <th className={`${subHead} ${REGIME_WASH[regime]} band-inset-r pr-3`}>Median</th>
            <th className={subHead}>Hit</th>
            <th className={subHead}>Median</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => {
            const s4 = cellStats(asset, "glci", regime, "4");
            const s13 = cellStats(asset, "glci", regime, "13");
            const s26 = cellStats(asset, "glci", regime, "26");
            const b13 = baseRate(asset, "13");
            return (
              <tr key={asset.id} className="border-b border-border">
                <td className="py-3 pr-3 align-top">
                  <span className="text-sm font-medium">{asset.name}</span>
                  <span className="block text-[0.6875rem] leading-4 text-muted-foreground">
                    {asset.category}
                  </span>
                </td>
                <HitCell stats={s4} pairedInference={pairedInference} />
                <MedianCell stats={s4} />
                <HitCell stats={s13} pairedInference={pairedInference} />
                <td className="py-3 pl-5 text-right align-top">
                  <span className="font-mono text-sm tabular-nums text-muted-foreground">
                    {hitPct(b13?.hit_rate)}
                  </span>
                </td>
                <EdgeCell stats={s13} pairedInference={pairedInference} />
                <MedianCell stats={s13} className="pr-3" />
                <HitCell stats={s26} pairedInference={pairedInference} />
                <MedianCell stats={s26} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 3: hit rates across all three regimes at 13 weeks
// ---------------------------------------------------------------------------

function RegimeComparisonTable({
  assets,
  currentRegime,
}: {
  assets: BacktestAssetResult[];
  currentRegime: Regime;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] max-w-3xl border-collapse">
        <thead>
          <tr>
            <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Asset
            </th>
            {REGIME_ORDER.map((r) => (
              <th
                key={r}
                className={`border-b border-border pb-2 pl-6 pr-3 text-right font-sans text-[0.6875rem] font-semibold uppercase tracking-wider ${REGIME_WASH[r]} ${REGIME_TEXT[r]} band-inset-x`}
              >
                {regimeLabel(r)}
                {r === currentRegime && (
                  <span className="ml-1.5 font-normal normal-case tracking-normal opacity-80">
                    · current
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id} className="border-b border-border">
              <td className="py-3 pr-3 text-sm font-medium">{asset.name}</td>
              {REGIME_ORDER.map((r) => {
                const s = cellStats(asset, "glci", r, "13");
                return (
                  <td
                    key={r}
                    className={`py-3 pl-6 pr-3 text-right align-top ${
                      r === currentRegime ? `${REGIME_WASH[r]} band-inset-x` : ""
                    }`}
                  >
                    <span className="font-mono text-sm tabular-nums">{hitPct(s?.hit_rate)}</span>
                    <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
                      {medPct(s?.median)} · n {s?.n ?? "–"}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 4: GLCI vs NFCI comparison at 13 weeks
// ---------------------------------------------------------------------------

const HEADLINE_ASSETS = ["sp500_price", "gold_price", "bitcoin_price"];

function ClassifierEdgeCell({
  asset,
  classifier,
  regime,
  pairedInference,
}: {
  asset: BacktestAssetResult;
  classifier: string;
  regime: Regime;
  pairedInference: boolean;
}) {
  const stats = cellStats(asset, classifier, regime, "13");
  const sig = edgeSignificant(stats, pairedInference);
  const edge = stats?.edge ?? null;
  const tone =
    sig && edge != null && stats?.ci_edge_low != null
      ? stats.ci_edge_low > 0
        ? "text-positive"
        : "text-negative"
      : "text-muted-foreground";
  return (
    <td className="py-2.5 pl-6 text-right align-baseline">
      <span className={`font-mono text-sm tabular-nums ${tone}`}>
        {edgePp(edge)}
        {sig === false && (
          <>
            {" "}
            <span className="font-mono text-[0.625rem] text-muted-foreground">n.s.</span>
          </>
        )}
      </span>
      <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
        n {stats?.n ?? "–"}
      </span>
      {pairedInference && stats?.ci_edge_low != null && stats?.ci_edge_high != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          paired CI {edgePp(stats.ci_edge_low)} to {edgePp(stats.ci_edge_high)}
        </span>
      )}
      {pairedInference && sig == null && edge != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          CI unavailable
        </span>
      )}
    </td>
  );
}

function ClassifierComparisonTable({
  assets,
  regime,
  pairedInference,
}: {
  assets: BacktestAssetResult[];
  regime: Regime;
  pairedInference: boolean;
}) {
  const headline = HEADLINE_ASSETS.map((id) => assets.find((a) => a.id === id))
    .filter((a): a is BacktestAssetResult => a != null)
    // An empty NFCI cell makes the comparison meaningless for that asset.
    .filter((a) => (cellStats(a, "nfci", regime, "13")?.n ?? 0) > 0);
  if (!headline.length) return null;

  const head =
    "border-b border-border pb-2 pl-6 text-right font-sans text-[0.6875rem] font-medium text-muted-foreground";

  return (
    <table className="w-full max-w-xl border-collapse">
      <thead>
        <tr>
          <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
            13w hit-rate edge, {regime} regime
          </th>
          <th className={head}>GLCI</th>
          <th className={head}>NFCI</th>
        </tr>
      </thead>
      <tbody>
        {headline.map((asset) => (
          <tr key={asset.id} className="border-b border-border">
            <td className="py-2.5 pr-3 text-sm font-medium">{asset.name}</td>
            <ClassifierEdgeCell
              asset={asset}
              classifier="glci"
              regime={regime}
              pairedInference={pairedInference}
            />
            <ClassifierEdgeCell
              asset={asset}
              classifier="nfci"
              regime={regime}
              pairedInference={pairedInference}
            />
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Section 5: risk profile footnote (renders whatever assets the payload has)
// ---------------------------------------------------------------------------

function RiskRow({ asset }: { asset: AssetRiskMetrics }) {
  const items: { label: string; value: string; tone?: string }[] = [
    {
      label: "Ann. return",
      value: `${signed(asset.annualized_return, 1)}%`,
      tone: asset.annualized_return >= 0 ? "text-positive" : "text-negative",
    },
    { label: "Ann. volatility", value: `${num(asset.annualized_volatility)}%` },
    { label: "Sharpe (1y)", value: num(asset.current_sharpe, 2) },
    { label: "Max drawdown", value: `${num(asset.max_drawdown)}%`, tone: "text-negative" },
    { label: "Corr. with GLCI", value: num(asset.correlation_with_glci, 2) },
    { label: "Sharpe · loose", value: num(asset.sharpe_by_regime.loose, 2) },
    { label: "Sharpe · neutral", value: num(asset.sharpe_by_regime.neutral, 2) },
    { label: "Sharpe · tight", value: num(asset.sharpe_by_regime.tight, 2) },
  ];

  return (
    <div className="grid gap-x-8 gap-y-3 border-t border-border py-4 sm:grid-cols-[14rem_1fr]">
      <div>
        <span className="text-sm font-medium">{asset.name}</span>
        <span className="block text-[0.6875rem] leading-4 text-muted-foreground">
          {asset.category}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label}>
            <dt className="text-[0.6875rem] text-muted-foreground">{item.label}</dt>
            <dd className={`font-mono text-sm tabular-nums ${item.tone ?? ""}`}>{item.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function PlaybookSkeleton() {
  return (
    <div className="animate-pulse space-y-6 pt-10 sm:pt-14" aria-label="Loading the playbook">
      <div className="h-4 w-56 rounded bg-muted" />
      <div className="h-12 w-3/4 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-5 w-full max-w-2xl rounded bg-muted" />
        <div className="h-5 w-2/3 max-w-xl rounded bg-muted" />
      </div>
      <div className="h-80 w-full rounded bg-muted" />
      <div className="h-48 w-full max-w-3xl rounded bg-muted" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PlaybookPage() {
  const backtest = useBacktestData();
  const risk = useRiskData();
  const canonical = useCanonicalRegime();

  const classifierRegime: Regime | null =
    backtest.data?.classifiers?.glci?.current_regime ?? null;

  const regime: Regime =
    canonical.regime ??
    classifierRegime ??
    risk.data?.current_regime ??
    "neutral";

  const regimesDiverge =
    canonical.regime != null &&
    classifierRegime != null &&
    canonical.regime !== classifierRegime;

  const lead = useMemo(
    () => playbookSentence(backtest.data, regime),
    [backtest.data, regime]
  );

  const bothFailed = Boolean(backtest.error && risk.error);
  const stillLoading =
    canonical.isLoading ||
    (backtest.isLoading && !backtest.data) ||
    (Boolean(backtest.error) && risk.isLoading && !risk.data);

  if (bothFailed) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-8">
        <DataLoadError title="The playbook could not be loaded" onRetry={backtest.refetch} />
      </div>
    );
  }

  if (stillLoading) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
        <PlaybookSkeleton />
      </div>
    );
  }

  const data = backtest.data;
  const pairedInference = data?.bootstrap_method === PAIRED_BOOTSTRAP_METHOD;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 sm:px-8">
      {/* Header */}
      <section className="pt-10 sm:pt-14">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
            The Playbook
            {data?.date_range?.end && ` · Backtest through ${formatShortDate(data.date_range.end)}`}
          </span>
          <RegimeStamp regime={regime} />
        </div>
        <h1 className="mt-4 max-w-4xl font-serif text-4xl font-medium leading-[1.08] tracking-tight sm:text-5xl">
          What has followed this regime.
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          {lead?.text ?? "Historical forward-return results are unavailable right now."}
        </p>
        <p className="mt-4 max-w-[80ch] font-serif text-[0.9375rem] leading-relaxed text-muted-foreground">
          Forward returns conditioned on expanding-threshold regime labels. The threshold step
          uses only composite observations through each week, but the upstream source data and
          factor estimates use the current vintage. This is reconstructed history, not a
          point-in-time record, and it can change.
        </p>
      </section>

      {regimesDiverge && classifierRegime && (
        <aside className="mt-8 border-y border-border py-4" aria-label="Classifier disagreement">
          <p className="font-mono text-xs uppercase tracking-[0.12em] text-negative">
            Classifier disagreement
          </p>
          <p className="mt-2 max-w-[80ch] font-serif text-[1.0625rem] leading-relaxed">
            The published index reads {regime}, while the backtest&apos;s expanding-window
            classifier reads {classifierRegime}
            {data?.date_range?.end && ` through ${formatShortDate(data.date_range.end)}`}. Conditions
            are close enough to a boundary that the {regime} and {classifierRegime} columns deserve
            attention together; the first table uses the published {regime} label for the current
            decision frame.
          </p>
        </aside>
      )}

      {data ? (
        <>
          {/* Forward returns table */}
          <div className="rule mt-10" />
          <section className="mt-8">
            <h2 className="text-sm font-semibold tracking-tight">
              Forward returns in {regime} regimes
            </h2>
            <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
              {pairedInference
                ? "Hit-rate CIs describe the regime subgroup. Edge is that subgroup hit rate minus the unconditional rate over the same classifier-eligible weeks; it is colored only when its separate paired 95% CI excludes zero."
                : "Hit rates and edges are descriptive. This published backtest predates the paired-inference schema, so confidence intervals and significance markers stay hidden until the data refreshes."}
            </p>
            <div className="mt-5">
              <ForwardReturnsTable
                assets={data.assets}
                regime={regime}
                pairedInference={pairedInference}
              />
            </div>
            <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
              GLCI classifier · medians are forward returns over the horizon
              {pairedInference ? " · n.s. = the paired edge CI includes zero" : ""} · cells
              condition on the signal-date regime
              {data.entry_lag_weeks === 1
                ? " · returns enter on the next weekly bar"
                : (data.entry_lag_weeks ?? 0) > 1
                  ? ` · returns enter ${data.entry_lag_weeks} weekly bars after the signal`
                  : ""}
            </p>
          </section>

          {/* Regime comparison */}
          <div className="rule mt-10" />
          <section className="mt-8">
            <h2 className="text-sm font-semibold tracking-tight">
              The same assets across all three regimes
            </h2>
            <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
              13-week subgroup hit rates by regime. Compare the columns descriptively; paired edge
              inference is reported separately.
            </p>
            <div className="mt-5">
              <RegimeComparisonTable assets={data.assets} currentRegime={regime} />
            </div>
            <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
              GLCI classifier · 13-week horizon · small figures are median return and sample size
            </p>
          </section>

          {/* Method and limits */}
          <div className="rule mt-10" />
          <section className="mt-8">
            <h2 className="text-sm font-semibold tracking-tight">
              What the backtest does and does not prove
            </h2>
            <div className="mt-4 max-w-[70ch] space-y-4 font-serif text-[1.0625rem] leading-relaxed">
              <p>
                The regime-label step uses an expanding-window z-score: its mean and standard
                deviation use only composite observations up to that week, with a one-year burn-in
                before any label is emitted. Tight is below −1, loose above +1, and neutral in
                between. This protects the threshold calculation from future composite
                observations, but it does not make the full pipeline point-in-time. Source series
                can be revised and the factor model is re-estimated on the current sample, so past
                composite values and labels can change.
              </p>
              <p>
                Because consecutive forward windows overlap (next week&apos;s 13-week return shares
                12 weeks with this one), naive standard errors would overstate confidence. The
                paired bootstrap resamples contiguous blocks from the full weekly calendar,
                keeping returns and regime labels together. Each draw recomputes both the regime
                subgroup and unconditional hit rates over that classifier&apos;s labeled weeks; their
                within-draw difference forms the edge CI. Sample sizes are printed in every cell
                because a 100% hit rate on 20 observations is a curiosity, not a strategy.
              </p>
              {!pairedInference && (
                <p>
                  The current payload does not identify that paired method, so this page
                  deliberately withholds its older intervals and all significance markers. Paired
                  inference will appear after the backtest is regenerated under the current
                  schema.
                </p>
              )}
              <p>
                The honest benchmark is the Chicago Fed&apos;s NFCI, a well-known financial
                conditions index run through the same classifier with the same thresholds. The
                comparison below shows each classifier&apos;s edge at 13 weeks
                {pairedInference ? " with its own paired interval" : " descriptively"}. It does
                not estimate an interval for the difference between GLCI and NFCI.
              </p>
            </div>
            <div className="mt-5">
              <ClassifierComparisonTable
                assets={data.assets}
                regime={regime}
                pairedInference={pairedInference}
              />
            </div>
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              {pairedInference
                ? "Read the n.s. markers literally: where they appear, the paired interval does not establish a nonzero edge at the 95% level. "
                : "No inferential claim is shown for this transitional payload. "}
              This is a backtest on one historical sample; past regimes may not repeat.
            </p>
          </section>

          {/* Risk profile footnote */}
          {risk.data && risk.data.assets.length > 0 && (
            <>
              <div className="rule mt-10" />
              <section className="mt-8">
                <h2 className="text-sm font-semibold tracking-tight">Risk profile</h2>
                <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
                  Full-sample risk statistics for the assets with computed metrics. Sharpe ratios
                  use a 252-day window and the 3-month Treasury as the risk-free rate.
                </p>
                <div className="mt-5">
                  {risk.data.assets.map((asset) => (
                    <RiskRow key={asset.id} asset={asset} />
                  ))}
                </div>
                <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
                  Regime Sharpes condition daily returns on the GLCI regime in force · max drawdown
                  is peak to trough over the full sample
                </p>
              </section>
            </>
          )}
        </>
      ) : (
        <>
          <div className="rule mt-10" />
          <p className="mt-8 max-w-[70ch] font-serif text-[1.0625rem] italic leading-relaxed text-muted-foreground">
            The backtest payload could not be loaded, so the forward-return tables are unavailable
            right now.
          </p>
          {risk.data && risk.data.assets.length > 0 && (
            <>
              <div className="rule mt-10" />
              <section className="mt-8">
                <h2 className="text-sm font-semibold tracking-tight">Risk profile</h2>
                <div className="mt-5">
                  {risk.data.assets.map((asset) => (
                    <RiskRow key={asset.id} asset={asset} />
                  ))}
                </div>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
