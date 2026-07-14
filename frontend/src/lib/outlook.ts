import type {
  BacktestAssetResult,
  BacktestHorizon,
  BacktestResponse,
  BacktestStats,
  FlowDestination,
  FlowsResponse,
  Regime,
} from "@/lib/api";

export const PAIRED_BOOTSTRAP_METHOD = "paired_full_calendar_moving_block";
export const PRODUCTION_GLCI_REGIME_METHOD = "rolling_104_period_zscore";

const HORIZON_PREFERENCE: BacktestHorizon[] = ["13", "4", "26"];
const DEFAULT_MIN_OBSERVATIONS = 20;
const MAX_ALIGNMENT_GAP_DAYS = 7;
const POSITIVE_HIT_THRESHOLD = 0.55;
const NEGATIVE_HIT_THRESHOLD = 0.45;

export type HistoricalDirection = "positive" | "mixed" | "negative";
export type EdgeEvidence = "positive" | "negative" | "unclear" | "unavailable" | "descriptive";
export type PriceDirection =
  | "leading"
  | "leading_fading"
  | "weak"
  | "weak_rebounding"
  | "mixed"
  | "unavailable";
export type CombinedRead =
  | "best_supported"
  | "aligned_descriptive"
  | "history_waiting"
  | "price_led"
  | "regime_headwind"
  | "mixed"
  | "least_supported";

export interface AssetOutlook {
  id: string;
  name: string;
  category: string;
  stats: BacktestStats;
  baseHitRate: number | null;
  historicalDirection: HistoricalDirection;
  edgeEvidence: EdgeEvidence;
  flow: FlowDestination | null;
  priceDirection: PriceDirection;
  combinedRead: CombinedRead;
}

export interface DirectionalOutlook {
  regime: Regime;
  horizon: BacktestHorizon | null;
  assets: AssetOutlook[];
  positive: AssetOutlook[];
  negative: AssetOutlook[];
  featured: AssetOutlook[];
  hasPositiveSupportedTilt: boolean;
  hasNegativeSupportedTilt: boolean;
  pairedInference: boolean;
  fdrInference: boolean;
  inferenceReady: boolean;
  multipleTestingAlpha: number | null;
  regimeAgreement: boolean | null;
  signalFresh: boolean;
  datesAligned: boolean;
  minObservations: number;
  preferredHorizonN: number | null;
}

function parseDate(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const value = new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();
  return Number.isFinite(value) ? value : null;
}

function datesWithinWeek(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = parseDate(a);
  const right = parseDate(b);
  if (left == null || right == null) return false;
  return Math.abs(left - right) <= MAX_ALIGNMENT_GAP_DAYS * 86_400_000;
}

function localDateISO(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function statsFor(
  asset: BacktestAssetResult,
  regime: Regime,
  horizon: BacktestHorizon
): BacktestStats | null {
  return asset.results?.glci?.[regime]?.[horizon] ?? null;
}

function isReportable(stats: BacktestStats | null): stats is BacktestStats {
  return Boolean(stats && stats.hit_rate != null && stats.median != null && stats.n > 0);
}

function selectHorizon(backtest: BacktestResponse, regime: Regime): BacktestHorizon | null {
  for (const horizon of HORIZON_PREFERENCE) {
    if (backtest.assets.some((asset) => isReportable(statsFor(asset, regime, horizon)))) {
      return horizon;
    }
  }
  return null;
}

function historicalDirection(stats: BacktestStats): HistoricalDirection {
  if (stats.hit_rate == null || stats.median == null) return "mixed";
  if (stats.hit_rate >= POSITIVE_HIT_THRESHOLD && stats.median > 0) return "positive";
  if (stats.hit_rate <= NEGATIVE_HIT_THRESHOLD && stats.median < 0) return "negative";
  return "mixed";
}

function edgeEvidence(
  stats: BacktestStats,
  pairedInference: boolean,
  fdrInference: boolean,
  inferenceReady: boolean
): EdgeEvidence {
  if (!pairedInference) return "descriptive";
  if (!fdrInference) return "unavailable";
  if (!inferenceReady) return "unavailable";
  if (stats.fdr_significant == null || stats.edge == null) return "unavailable";
  if (!stats.fdr_significant) return "unclear";
  if (stats.edge > 0) return "positive";
  if (stats.edge < 0) return "negative";
  return "unclear";
}

function priceDirection(flow: FlowDestination | null): PriceDirection {
  if (!flow || flow.flow_z == null) return "unavailable";
  const trailing = flow.ret_13w;
  const recent = flow.ret_4w;
  if (flow.flow_z >= 1 && trailing != null && trailing > 0) {
    if (recent == null) return "mixed";
    return recent > 0 ? "leading" : "leading_fading";
  }
  if (flow.flow_z <= -1 && trailing != null && trailing < 0) {
    if (recent == null) return "mixed";
    return recent >= 0 ? "weak_rebounding" : "weak";
  }
  return "mixed";
}

function combinedRead(
  history: HistoricalDirection,
  edge: EdgeEvidence,
  price: PriceDirection,
  canCombine: boolean
): CombinedRead {
  const leading = price === "leading";
  const weak = price === "weak";

  if (canCombine && history === "positive" && edge === "positive" && leading) {
    return "best_supported";
  }
  if (canCombine && (history === "negative" || edge === "negative") && weak) {
    return "least_supported";
  }
  if (edge === "negative") {
    return "regime_headwind";
  }
  if (canCombine && history === "positive" && leading) {
    return "aligned_descriptive";
  }
  if (history === "positive" && !weak) {
    return "history_waiting";
  }
  if (canCombine && leading && edge !== "positive") {
    return "price_led";
  }
  return "mixed";
}

const READ_ORDER: Record<CombinedRead, number> = {
  best_supported: 0,
  aligned_descriptive: 1,
  history_waiting: 2,
  price_led: 3,
  regime_headwind: 4,
  mixed: 5,
  least_supported: 6,
};

function compareOutlooks(a: AssetOutlook, b: AssetOutlook): number {
  const read = READ_ORDER[a.combinedRead] - READ_ORDER[b.combinedRead];
  if (read !== 0) return read;
  const hit = (b.stats.hit_rate ?? 0) - (a.stats.hit_rate ?? 0);
  if (hit !== 0) return hit;
  return (b.stats.median ?? 0) - (a.stats.median ?? 0);
}

export function buildDirectionalOutlook(
  backtest: BacktestResponse | null,
  flows: FlowsResponse | null,
  regime: Regime,
  signalDate?: string | null,
  evaluationDate = localDateISO()
): DirectionalOutlook | null {
  if (
    !backtest ||
    backtest.regime_threshold_method !== PRODUCTION_GLCI_REGIME_METHOD
  ) {
    return null;
  }

  const horizon = selectHorizon(backtest, regime);
  const pairedInference = backtest.bootstrap_method === PAIRED_BOOTSTRAP_METHOD;
  const fdrInference =
    backtest.inference?.multiple_testing_method === "benjamini_yekutieli";
  const inferenceReady =
    fdrInference && backtest.inference?.readiness?.ready === true;
  const multipleTestingAlpha = fdrInference
    ? (backtest.inference?.multiple_testing_alpha ?? null)
    : null;
  const classifierRegime = backtest.classifiers?.glci?.current_regime ?? null;
  const regimeAgreement = classifierRegime == null ? null : classifierRegime === regime;
  const signalFresh = datesWithinWeek(signalDate, evaluationDate);
  const backtestAligned = signalDate
    ? datesWithinWeek(backtest.date_range?.end, signalDate) &&
      datesWithinWeek(backtest.date_range?.end, evaluationDate)
    : false;
  const flowsAligned = !flows
    ? true
    : signalDate
      ? datesWithinWeek(flows.as_of, signalDate) &&
        datesWithinWeek(flows.as_of, evaluationDate)
      : false;
  const datesAligned = backtestAligned && flowsAligned;
  const minObservations = backtest.min_obs_per_regime ?? DEFAULT_MIN_OBSERVATIONS;
  const preferredHorizonN = Math.max(
    0,
    ...backtest.assets.map((asset) => statsFor(asset, regime, "13")?.n ?? 0)
  ) || null;

  if (!horizon) {
    return {
      regime,
      horizon: null,
      assets: [],
      positive: [],
      negative: [],
      featured: [],
      hasPositiveSupportedTilt: false,
      hasNegativeSupportedTilt: false,
      pairedInference,
      fdrInference,
      inferenceReady,
      multipleTestingAlpha,
      regimeAgreement,
      signalFresh,
      datesAligned,
      minObservations,
      preferredHorizonN,
    };
  }

  const flowBySeries = new Map(
    (flows?.destinations ?? []).map((destination) => [destination.series_id, destination])
  );
  const assets = backtest.assets
    .map((asset): AssetOutlook | null => {
      const stats = statsFor(asset, regime, horizon);
      if (!isReportable(stats)) return null;
      const history = historicalDirection(stats);
      const edge = edgeEvidence(
        stats,
        pairedInference,
        fdrInference,
        inferenceReady
      );
      const candidateFlow = flowBySeries.get(asset.id) ?? null;
      const flowFresh = candidateFlow && signalDate
        ? datesWithinWeek(candidateFlow.last_date, signalDate) &&
          datesWithinWeek(candidateFlow.last_date, evaluationDate)
        : false;
      const flow = signalFresh && datesAligned && flowFresh ? candidateFlow : null;
      const price = priceDirection(flow);
      return {
        id: asset.id,
        name: asset.name,
        category: asset.category,
        stats,
        baseHitRate: asset.base_rates?.[horizon]?.hit_rate ?? null,
        historicalDirection: history,
        edgeEvidence: edge,
        flow,
        priceDirection: price,
        combinedRead: combinedRead(
          history,
          edge,
          price,
          regimeAgreement === true && signalFresh && datesAligned && Boolean(flow)
        ),
      };
    })
    .filter((asset): asset is AssetOutlook => asset != null)
    .sort(compareOutlooks);

  const positive = assets
    .filter(
      (asset) =>
        asset.historicalDirection === "positive" && asset.edgeEvidence !== "negative"
    )
    .sort((a, b) => (b.stats.hit_rate ?? 0) - (a.stats.hit_rate ?? 0));
  const negative = assets
    .filter((asset) => asset.historicalDirection === "negative")
    .sort((a, b) => (a.stats.hit_rate ?? 1) - (b.stats.hit_rate ?? 1));
  const featured = [
    ...assets.filter((asset) => asset.combinedRead === "best_supported"),
    ...assets.filter((asset) => asset.combinedRead === "aligned_descriptive"),
    ...positive,
    ...assets.filter((asset) => asset.combinedRead === "price_led"),
  ].filter((asset, index, list) => list.findIndex((item) => item.id === asset.id) === index);

  return {
    regime,
    horizon,
    assets,
    positive,
    negative,
    featured,
    hasPositiveSupportedTilt: assets.some(
      (asset) =>
        asset.historicalDirection === "positive" && asset.edgeEvidence === "positive"
    ),
    hasNegativeSupportedTilt: assets.some(
      (asset) => asset.edgeEvidence === "negative"
    ),
    pairedInference,
    fdrInference,
    inferenceReady,
    multipleTestingAlpha,
    regimeAgreement,
    signalFresh,
    datesAligned,
    minObservations,
    preferredHorizonN,
  };
}

export const COMBINED_READ_LABELS: Record<CombinedRead, string> = {
  best_supported: "Best supported now",
  aligned_descriptive: "History and price agree",
  history_waiting: "Positive history; price is not confirming",
  price_led: "Price is strong; regime history is not",
  regime_headwind: "This regime reduced its usual hit rate",
  mixed: "Mixed evidence",
  least_supported: "History and price are both weak",
};

export const PRICE_DIRECTION_LABELS: Record<PriceDirection, string> = {
  leading: "leading and still rising",
  leading_fading: "leading, but fading over four weeks",
  weak: "weak and still falling",
  weak_rebounding: "weak, but rebounding over four weeks",
  mixed: "near its own norm",
  unavailable: "not available",
};
