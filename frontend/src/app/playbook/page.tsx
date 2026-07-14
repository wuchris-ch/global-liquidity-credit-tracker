"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useBacktestData } from "@/hooks/use-backtest-data";
import { useFlowsData } from "@/hooks/use-flows-data";
import { useRiskData } from "@/hooks/use-risk-data";
import { RegimeStamp, regimeLabel } from "@/components/regime-stamp";
import { DataLoadError } from "@/components/data-load-error";
import { DirectionalOutlookView } from "@/components/directional-outlook";
import { formatShortDate } from "@/lib/data-status";
import { signed } from "@/lib/brief";
import {
  buildDirectionalOutlook,
  PAIRED_BOOTSTRAP_METHOD,
  PRODUCTION_GLCI_REGIME_METHOD,
} from "@/lib/outlook";
import api from "@/lib/api";
import type {
  AssetRiskMetrics,
  BacktestAssetResult,
  BacktestBaseRate,
  BacktestHorizon,
  BacktestLiveEvaluation,
  BacktestStats,
  Regime,
} from "@/lib/api";

/**
 * The canonical current regime is the one published by the GLCI endpoint
 * (104-week rolling z-score), which the backtest now reproduces exactly.
 * Keeping the independent read still catches stale or mismatched payloads.
 */
function useCanonicalRegime(): { regime: Regime | null; date: string | null; isLoading: boolean } {
  const [regime, setRegime] = useState<Regime | null>(null);
  const [date, setDate] = useState<string | null>(null);
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
        setDate(latest.date ?? null);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { regime, date, isLoading };
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

/** Format a scheduled date without clamping future dates to today. */
function scheduledDate(date: string): string {
  const [year, month, day] = date.slice(0, 10).split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return "unknown";
  const parsed = new Date(year, month - 1, day);
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(year === new Date().getFullYear() ? {} : { year: "numeric" }),
  });
}

const REGIME_ORDER: Regime[] = ["loose", "neutral", "tight"];
const HORIZON_ORDER: BacktestHorizon[] = ["4", "13", "26"];

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

/** Only multiplicity-controlled cells qualify as supported evidence. */
function edgeSupported(
  stats: BacktestStats | null,
  pairedInference: boolean,
  fdrInference: boolean,
  inferenceReady: boolean
): boolean | null {
  if (
    !pairedInference ||
    !fdrInference ||
    !inferenceReady ||
    !stats ||
    stats.edge == null ||
    typeof stats.fdr_significant !== "boolean"
  ) {
    return null;
  }
  return stats.fdr_significant;
}

function qValue(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "q unavailable";
  return v < 0.001 ? "q < 0.001" : `q ${v.toFixed(3)}`;
}

// ---------------------------------------------------------------------------
// Table cells
// ---------------------------------------------------------------------------

/** Hit rate with sample size in small muted type underneath. */
function HitCell({
  stats,
  pairedInference,
  className = "",
}: {
  stats: BacktestStats | null;
  pairedInference: boolean;
  className?: string;
}) {
  return (
    <td className={`py-3 pl-5 text-right align-top ${className}`}>
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
 * Edge vs base rate: colored only when it survives the published FDR
 * procedure. The nominal paired interval remains visible underneath.
 */
function EdgeCell({
  stats,
  pairedInference,
  fdrInference,
  inferenceReady,
  className = "",
}: {
  stats: BacktestStats | null;
  pairedInference: boolean;
  fdrInference: boolean;
  inferenceReady: boolean;
  className?: string;
}) {
  const supported = edgeSupported(
    stats,
    pairedInference,
    fdrInference,
    inferenceReady
  );
  const edge = stats?.edge ?? null;
  const tone =
    supported && edge != null
      ? edge > 0
        ? "text-positive"
        : "text-negative"
      : "text-muted-foreground";
  return (
    <td className={`py-3 pl-5 text-right align-top ${className}`}>
      <span className={`font-mono text-sm tabular-nums ${tone}`}>
        {edgePp(edge)}
        {supported === false && (
          <>
            {" "}
            <span className="font-mono text-[0.625rem] text-muted-foreground">FDR n.s.</span>
          </>
        )}
      </span>
      {fdrInference && stats?.q_value != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          BY {qValue(stats.q_value)}
        </span>
      )}
      {fdrInference && !inferenceReady && edge != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          evidence-readiness gate not met
        </span>
      )}
      {pairedInference && stats?.ci_edge_low != null && stats?.ci_edge_high != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          paired CI {edgePp(stats.ci_edge_low)} to {edgePp(stats.ci_edge_high)}
        </span>
      )}
      {pairedInference && supported == null && edge != null && !(fdrInference && !inferenceReady) && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          FDR decision unavailable
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
  fdrInference,
  inferenceReady,
  focusHorizon,
}: {
  assets: BacktestAssetResult[];
  regime: Regime;
  pairedInference: boolean;
  fdrInference: boolean;
  inferenceReady: boolean;
  focusHorizon: BacktestHorizon;
}) {
  const groupHead = "pb-1 pl-5 text-left font-sans text-[0.6875rem] font-semibold uppercase tracking-wider";
  const subHead =
    "border-b border-border pb-2 pl-5 text-right font-sans text-[0.6875rem] font-medium text-muted-foreground";

  const band = (horizon: BacktestHorizon) =>
    horizon === focusHorizon ? `${REGIME_WASH[regime]} ${REGIME_TEXT[regime]}` : "";

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] border-collapse">
        <thead>
          <tr>
            <th className="pb-1 text-left" />
            {HORIZON_ORDER.map((horizon) => (
              <th
                key={horizon}
                colSpan={horizon === focusHorizon ? 4 : 2}
                className={`${groupHead} ${
                  horizon === focusHorizon
                    ? `${band(horizon)} band-inset-x`
                    : "text-muted-foreground"
                }`}
              >
                {horizon} weeks
                {horizon === focusHorizon && ` · ${regimeLabel(regime)} read`}
              </th>
            ))}
          </tr>
          <tr>
            <th className="border-b border-border pb-2 text-left font-sans text-[0.6875rem] font-medium text-muted-foreground">
              Asset
            </th>
            {HORIZON_ORDER.map((horizon) => {
              const focused = horizon === focusHorizon;
              const wash = focused ? REGIME_WASH[regime] : "";
              return (
                <Fragment key={horizon}>
                  <th className={`${subHead} ${wash} ${focused ? "band-inset-l" : ""}`}>
                    Hit
                  </th>
                  {focused && <th className={`${subHead} ${wash}`}>Base</th>}
                  {focused && <th className={`${subHead} ${wash}`}>Edge</th>}
                  <th className={`${subHead} ${wash} ${focused ? "band-inset-r pr-3" : ""}`}>
                    Median
                  </th>
                </Fragment>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => {
            return (
              <tr key={asset.id} className="border-b border-border">
                <td className="py-3 pr-3 align-top">
                  <span className="text-sm font-medium">{asset.name}</span>
                  <span className="block text-[0.6875rem] leading-4 text-muted-foreground">
                    {asset.category}
                  </span>
                </td>
                {HORIZON_ORDER.map((horizon) => {
                  const stats = cellStats(asset, "glci", regime, horizon);
                  const base = baseRate(asset, horizon);
                  const focused = horizon === focusHorizon;
                  const wash = focused ? REGIME_WASH[regime] : "";
                  return (
                    <Fragment key={horizon}>
                      <HitCell
                        stats={stats}
                        pairedInference={pairedInference}
                        className={`${wash} ${focused ? "band-inset-l" : ""}`}
                      />
                      {focused && (
                        <td className={`py-3 pl-5 text-right align-top ${wash}`}>
                          <span className="font-mono text-sm tabular-nums text-muted-foreground">
                            {hitPct(base?.hit_rate)}
                          </span>
                        </td>
                      )}
                      {focused && (
                        <EdgeCell
                          stats={stats}
                          pairedInference={pairedInference}
                          fdrInference={fdrInference}
                          inferenceReady={inferenceReady}
                          className={wash}
                        />
                      )}
                      <MedianCell
                        stats={stats}
                        className={`${wash} ${focused ? "band-inset-r pr-3" : ""}`}
                      />
                    </Fragment>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 3: hit rates across all three regimes at the active horizon
// ---------------------------------------------------------------------------

function RegimeComparisonTable({
  assets,
  currentRegime,
  horizon,
}: {
  assets: BacktestAssetResult[];
  currentRegime: Regime;
  horizon: BacktestHorizon;
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
                const s = cellStats(asset, "glci", r, horizon);
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
  fdrInference,
  inferenceReady,
}: {
  asset: BacktestAssetResult;
  classifier: string;
  regime: Regime;
  pairedInference: boolean;
  fdrInference: boolean;
  inferenceReady: boolean;
}) {
  const stats = cellStats(asset, classifier, regime, "13");
  const supported = edgeSupported(
    stats,
    pairedInference,
    fdrInference,
    inferenceReady
  );
  const edge = stats?.edge ?? null;
  const tone =
    supported && edge != null
      ? edge > 0
        ? "text-positive"
        : "text-negative"
      : "text-muted-foreground";
  return (
    <td className="py-2.5 pl-6 text-right align-baseline">
      <span className={`font-mono text-sm tabular-nums ${tone}`}>
        {edgePp(edge)}
        {supported === false && (
          <>
            {" "}
            <span className="font-mono text-[0.625rem] text-muted-foreground">FDR n.s.</span>
          </>
        )}
      </span>
      <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
        n {stats?.n ?? "–"}
      </span>
      {fdrInference && stats?.q_value != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          BY {qValue(stats.q_value)}
        </span>
      )}
      {fdrInference && !inferenceReady && edge != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          evidence-readiness gate not met
        </span>
      )}
      {pairedInference && stats?.ci_edge_low != null && stats?.ci_edge_high != null && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          paired CI {edgePp(stats.ci_edge_low)} to {edgePp(stats.ci_edge_high)}
        </span>
      )}
      {pairedInference && supported == null && edge != null && !(fdrInference && !inferenceReady) && (
        <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
          FDR decision unavailable
        </span>
      )}
    </td>
  );
}

function ClassifierComparisonTable({
  assets,
  regime,
  pairedInference,
  fdrInference,
  inferenceReady,
}: {
  assets: BacktestAssetResult[];
  regime: Regime;
  pairedInference: boolean;
  fdrInference: boolean;
  inferenceReady: boolean;
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
              fdrInference={fdrInference}
              inferenceReady={inferenceReady}
            />
            <ClassifierEdgeCell
              asset={asset}
              classifier="nfci"
              regime={regime}
              pairedInference={pairedInference}
              fdrInference={fdrInference}
              inferenceReady={inferenceReady}
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
      label: "Annual return",
      value: `${signed(asset.annualized_return, 1)}%`,
      tone: asset.annualized_return >= 0 ? "text-positive" : "text-negative",
    },
    { label: "Annual volatility", value: `${num(asset.annualized_volatility)}%` },
    { label: "Full-sample Sharpe", value: num(asset.current_sharpe, 2) },
    { label: "Max drawdown", value: `${num(asset.max_drawdown)}%`, tone: "text-negative" },
    { label: "Weekly GLCI-change corr.", value: num(asset.correlation_with_glci, 2) },
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

function LiveHorizonCell({
  result,
  minObservations,
}: {
  result: BacktestLiveEvaluation["assets"][number]["horizons"][string] | undefined;
  minObservations: number;
}) {
  if (!result) {
    return <td className="py-3 pl-5 text-right font-mono text-sm text-muted-foreground">–</td>;
  }

  const reportableRegimes = (["tight", "neutral", "loose"] as const)
    .map((regime) => ({ regime, stats: result.by_regime?.[regime] }))
    .filter(
      (item) =>
        item.stats?.status === "reportable" &&
        item.stats.median != null &&
        item.stats.hit_rate != null
    );
  return (
    <td className="py-3 pl-5 text-right align-top">
      {reportableRegimes.length > 0 ? (
        <>
          {reportableRegimes.map(({ regime, stats }) => (
            <span key={regime} className="block font-mono text-sm tabular-nums">
              {regimeLabel(regime)} {hitPct(stats?.hit_rate)} hit · {medPct(stats?.median)} median
              <span className="block text-[0.625rem] leading-4 text-muted-foreground">
                n {stats?.matured ?? 0}
              </span>
            </span>
          ))}
          <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
            all signals {result.matured} matured · {result.pending} pending
            {result.unavailable > 0 ? ` · ${result.unavailable} unavailable` : ""}
          </span>
        </>
      ) : (
        <>
          <span className="block font-mono text-sm tabular-nums text-muted-foreground">
            {result.matured}/{minObservations} matured
          </span>
          <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
            {result.pending} pending of {result.issued} issued
            {result.unavailable > 0 ? ` · ${result.unavailable} unavailable` : ""}
          </span>
          {result.next_maturity_date && (
            <span className="block font-mono text-[0.625rem] leading-4 text-muted-foreground">
              next {scheduledDate(result.next_maturity_date)}
            </span>
          )}
        </>
      )}
    </td>
  );
}

function ObservedLiveRecord({ evaluation }: { evaluation: BacktestLiveEvaluation }) {
  const { ledger, methodology } = evaluation;
  const statusLabel =
    evaluation.status === "reportable"
      ? "Reportable"
      : evaluation.status === "collecting"
        ? "Collecting evidence"
        : "Unavailable";

  return (
    <section className="mt-8" aria-labelledby="observed-live-record-title">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 id="observed-live-record-title" className="text-sm font-semibold tracking-tight">
          Observed live record
        </h2>
        <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-muted-foreground">
          {statusLabel}
        </span>
      </div>
      {evaluation.status === "unavailable" ? (
        <p className="mt-3 max-w-[70ch] font-serif text-[0.9375rem] italic leading-relaxed text-muted-foreground">
          The published payload cannot evaluate recorded signals against later returns yet.
        </p>
      ) : (
        <>
          <p className="mt-3 max-w-[75ch] font-serif text-[1.0625rem] leading-relaxed">
            The ledger contains {ledger.unique_signal_dates} unique signal {ledger.unique_signal_dates === 1 ? "date" : "dates"} across {ledger.vintage_count} recorded {ledger.vintage_count === 1 ? "vintage" : "vintages"}
            {ledger.duplicate_vintages > 0
              ? `, including ${ledger.duplicate_vintages} later recomputations`
              : ""}.
            {evaluation.status === "collecting"
              ? ` Regime-conditioned outcomes stay hidden until at least ${methodology.min_observations} have matured for an asset, horizon, and regime.`
              : " At least one asset, horizon, and regime now clears the reporting minimum."}
          </p>
          {(ledger.first_signal_date || ledger.latest_signal_date) && (
            <p className="mt-1.5 font-mono text-xs text-muted-foreground">
              Recorded signal dates {formatShortDate(ledger.first_signal_date)} to {formatShortDate(ledger.latest_signal_date)}
            </p>
          )}
          {evaluation.assets.length > 0 && (
            <div className="mt-5 overflow-x-auto">
              <table className="w-full min-w-[46rem] border-collapse text-left">
                <thead>
                  <tr className="border-b border-border">
                    <th className="pb-2 text-xs font-medium text-muted-foreground">Asset</th>
                    {HORIZON_ORDER.map((horizon) => (
                      <th
                        key={horizon}
                        className="pb-2 pl-5 text-right text-xs font-medium text-muted-foreground"
                      >
                        {horizon} weeks
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {evaluation.assets.map((asset) => (
                    <tr key={asset.id} className="border-b border-border/60 last:border-b-0">
                      <th scope="row" className="py-3 pr-5 align-top text-sm font-medium">
                        {asset.name}
                        <span className="block text-[0.6875rem] font-normal leading-4 text-muted-foreground">
                          {asset.category}
                        </span>
                      </th>
                      {HORIZON_ORDER.map((horizon) => (
                        <LiveHorizonCell
                          key={horizon}
                          result={asset.horizons?.[horizon]}
                          minObservations={methodology.min_observations}
                        />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-4 max-w-[75ch] font-serif text-sm leading-relaxed text-muted-foreground">
            One signal per date is frozen at its first publication, before the evaluated outcome,
            and entry waits for the first complete Friday bar after publication. This record is
            forward-safe, but the underlying source series and realized adjusted-price outcomes
            are not yet stored as complete immutable vintages.
          </p>
        </>
      )}
    </section>
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
  const flows = useFlowsData();
  const risk = useRiskData();
  const canonical = useCanonicalRegime();
  const productionBacktest =
    backtest.data?.regime_threshold_method === PRODUCTION_GLCI_REGIME_METHOD
      ? backtest.data
      : null;

  const classifierRegime: Regime | null =
    productionBacktest?.classifiers?.glci?.current_regime ?? null;

  const regime: Regime =
    canonical.regime ??
    classifierRegime ??
    risk.data?.current_regime ??
    "neutral";

  const regimesDiverge =
    canonical.regime != null &&
    classifierRegime != null &&
    canonical.regime !== classifierRegime;

  const outlook = useMemo(
    () =>
      buildDirectionalOutlook(
        productionBacktest,
        flows.data,
        regime,
        canonical.date ?? productionBacktest?.date_range?.end
      ),
    [productionBacktest, flows.data, regime, canonical.date]
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

  const data = productionBacktest;
  const legacyBacktestPayload = Boolean(backtest.data && !productionBacktest);
  const pairedInference = data?.bootstrap_method === PAIRED_BOOTSTRAP_METHOD;
  const fdrInference =
    data?.inference?.multiple_testing_method === "benjamini_yekutieli";
  const fdrAlpha = data?.inference?.multiple_testing_alpha ?? null;
  const inferenceReadiness = data?.inference?.readiness;
  const inferenceReady = inferenceReadiness?.ready === true;
  const focusHorizon = outlook?.horizon ?? "13";

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
          What may do well after this signal.
        </h1>
        <p className="mt-5 max-w-[70ch] font-serif text-lg leading-relaxed text-muted-foreground sm:text-xl">
          Start with the preferred reportable horizon: 13 weeks when available, then 4, then 26.
          Current price leadership is a separate confirmation check. The highlighted horizon shows
          hit rate, median, base rate, edge, paired edge CI, adjusted q-value, and sample size. Other
          horizons keep hit rate, median, and sample size visible for comparison.
        </p>
        <p className="mt-4 max-w-[80ch] font-serif text-[0.9375rem] leading-relaxed text-muted-foreground">
          These are conditional forward returns from reconstructed, current-vintage history, not a
          point-in-time forecast. The rolling classifier uses only composite readings through each
          signal week, but source revisions and factor re-estimation can still
          change the past.
        </p>
      </section>

      {regimesDiverge && classifierRegime && (
        <aside className="mt-8 border-y border-border py-4" aria-label="Classifier disagreement">
          <p className="font-mono text-xs uppercase tracking-[0.12em] text-negative">
            Classifier disagreement
          </p>
          <p className="mt-2 max-w-[80ch] font-serif text-[1.0625rem] leading-relaxed">
            The published index reads {regime}, while the backtest payload reads {classifierRegime}
            {data?.date_range?.end && ` through ${formatShortDate(data.date_range.end)}`}. The two
            payloads are not aligned and should not be combined until the backtest is regenerated;
            the first table keeps the published {regime} label as the current decision frame.
          </p>
        </aside>
      )}

      {data ? (
        <>
          {/* Directional read */}
          <div className="rule mt-10" />
          <section className="mt-8" aria-labelledby="directional-read-title">
            <h2 id="directional-read-title" className="text-sm font-semibold tracking-tight">
              What the evidence supports
            </h2>
            <p className="mt-0.5 max-w-[75ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
              History sets the direction; trailing price leadership can confirm or challenge it.
              Neither is a promise about the next return.
            </p>
            <div className="mt-5 max-w-4xl">
              {outlook ? (
                <DirectionalOutlookView outlook={outlook} />
              ) : (
                <p className="font-serif text-[0.9375rem] italic text-muted-foreground">
                  Historical forward-return results are unavailable right now.
                </p>
              )}
            </div>
          </section>

          {data.live_evaluation && (
            <>
              <div className="rule mt-10" />
              <ObservedLiveRecord evaluation={data.live_evaluation} />
            </>
          )}

          {/* Forward returns table */}
          <div className="rule mt-10" />
          <section className="mt-8">
            <h2 className="text-sm font-semibold tracking-tight">
              Forward returns in {regime} regimes
            </h2>
            <p className="mt-0.5 max-w-[70ch] font-serif text-[0.9375rem] italic leading-snug text-muted-foreground">
              {pairedInference
                ? fdrInference
                  ? inferenceReady
                    ? "Hit rate is the share of signals followed by a gain. Base rate is the asset's usual hit rate over the same eligible weeks. Edge is hit rate minus base rate; color appears only when that edge survives Benjamini-Yekutieli false-discovery-rate control."
                    : "Hit rate, edge, intervals, and q-values remain visible, but supported labels are withheld until point-in-time history and the sample-coverage gate are both available."
                  : "Hit rate is the share of signals followed by a gain. Base rate is the asset's usual hit rate over the same eligible weeks. This payload has paired intervals but no multiple-testing adjustment, so every edge remains descriptive."
                : "Hit rate is the share of signals followed by a gain. Base rate is the asset's usual hit rate, and edge is hit rate minus base rate. This older payload has no paired confidence intervals, so every edge is descriptive."}
            </p>
            <div className="mt-5">
              <ForwardReturnsTable
                assets={data.assets}
                regime={regime}
                pairedInference={pairedInference}
                fdrInference={fdrInference}
                inferenceReady={inferenceReady}
                focusHorizon={focusHorizon}
              />
            </div>
            <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
              Median = middle forward return · CI = confidence interval · n = sample size
              {fdrInference ? " · FDR n.s. = edge does not clear the adjusted threshold" : ""}
              {fdrInference && !inferenceReady ? " · evidence gate = support withheld" : ""} · cells
              use the signal-date GLCI regime
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
              {focusHorizon}-week subgroup hit rates by regime. Compare the columns descriptively;
              paired edge inference is reported separately.
            </p>
            <div className="mt-5">
              <RegimeComparisonTable
                assets={data.assets}
                currentRegime={regime}
                horizon={focusHorizon}
              />
            </div>
            <p className="mt-3 font-mono text-[0.6875rem] text-muted-foreground/80">
              GLCI classifier · {focusHorizon}-week horizon · small figures are median return and
              sample size
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
                <span className="font-medium">Regime labels.</span> The 104-week rolling z-score uses
                only composite readings available through each week, with a 20-week minimum.
                Tight is below −1σ, Loose is above +1σ, and Neutral is between them. This removes
                future composite readings from the threshold step, but the full pipeline is not
                point-in-time. Source revisions and factor re-estimation can change past values and
                labels.
              </p>
              <p>
                <span className="font-medium">Confidence intervals.</span> Forward windows overlap:
                next week&apos;s 13-week return shares 12 weeks with this one. A paired moving-block
                bootstrap resamples contiguous weeks, keeping returns and regime labels together.
                Each draw recomputes the regime hit rate, base rate, and their difference, which is
                the edge CI. Sample sizes stay visible because a 100% hit rate on 20 observations
                is a curiosity, not a strategy.
              </p>
              {fdrInference ? (
                <>
                  <p>
                    <span className="font-medium">Multiple comparisons.</span> The table tests many
                    classifier, asset, regime, and horizon combinations. Benjamini-Yekutieli control
                    is applied to the full family of {data.inference?.tests_in_family ?? "finite"}
                    {" "}tests at a {fdrAlpha == null ? "published" : `${Math.round(fdrAlpha * 100)}%`}
                    {" "}false-discovery-rate threshold. The q-value is the adjusted evidence measure;
                    a nominal paired interval by itself is not labeled supported.
                  </p>
                  <p>
                    <span className="font-medium">Evidence readiness.</span>{" "}
                    {inferenceReady
                      ? `The backtest is point-in-time, the primary GLCI classifier clears the ${inferenceReadiness?.minimum_classified_weeks ?? 260}-week history floor, and every regime has at least ${inferenceReadiness?.minimum_observations_per_regime ?? 20} observations.`
                      : `Support is withheld. Point-in-time source history is ${inferenceReadiness?.point_in_time_history ? "available" : "unavailable"}. The primary GLCI classifier has ${inferenceReadiness?.observed_classified_weeks ?? "an unavailable number of"} classified weeks versus a ${inferenceReadiness?.minimum_classified_weeks ?? 260}-week floor, with regime counts of tight ${inferenceReadiness?.regime_observations.tight ?? 0}, neutral ${inferenceReadiness?.regime_observations.neutral ?? 0}, and loose ${inferenceReadiness?.regime_observations.loose ?? 0}. The sample floor is a disclosed governance policy, not proof of a complete cycle.`}
                  </p>
                </>
              ) : pairedInference ? (
                <p>
                  This payload includes paired intervals but no multiple-testing adjustment. The
                  page therefore leaves every edge uncolored and makes no supported-edge claim.
                </p>
              ) : (
                <p>
                  The current payload does not identify that paired method, so this page
                  deliberately withholds its older intervals and all significance markers. Paired
                  inference will appear after the backtest is regenerated under the current
                  schema.
                </p>
              )}
              <p>
                <span className="font-medium">Benchmark.</span> The Chicago Fed&apos;s NFCI retains an
                expanding one-year classifier as an independent baseline. The comparison below shows each
                classifier&apos;s 13-week edge
                {fdrInference
                  ? " with its paired CI and family-adjusted q-value"
                  : pairedInference
                    ? " with its own paired CI"
                    : " descriptively"}. It does not estimate a CI for the difference between GLCI
                and NFCI.
              </p>
            </div>
            <div className="mt-5">
              <ClassifierComparisonTable
                assets={data.assets}
                regime={regime}
                pairedInference={pairedInference}
                fdrInference={fdrInference}
                inferenceReady={inferenceReady}
              />
            </div>
            <p className="mt-4 max-w-[70ch] font-serif text-[1.0625rem] leading-relaxed">
              {fdrInference
                ? inferenceReady
                  ? "Read FDR n.s. literally: the cell does not clear the Benjamini-Yekutieli adjusted threshold. "
                  : "Q-values are shown, but no cell is labeled supported until the point-in-time and sample-readiness gate is met. "
                : pairedInference
                  ? "The paired intervals are shown descriptively because this payload has no multiple-testing control. "
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
                  use excess returns over the 3-month Treasury rate.
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
            {legacyBacktestPayload
              ? "The published backtest still uses the retired expanding classifier. Forward-return tables are withheld until it is regenerated with the production rolling classifier."
              : "The backtest payload could not be loaded, so the forward-return tables are unavailable right now."}
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
