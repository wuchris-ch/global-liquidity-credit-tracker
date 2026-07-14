/**
 * API client for fetching data from the Python backend.
 */

// Allows pointing the frontend to static JSON (e.g., GitHub Pages) first,
// then falling back to a live API (dev/local).
const API_BASE_URL =
  (process.env.NEXT_PUBLIC_DATA_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000").replace(/\/$/, "");

const IS_STATIC = Boolean(process.env.NEXT_PUBLIC_DATA_BASE_URL);

/** True when the app reads pre-computed JSON (GitHub Pages) instead of a live API. */
export const isStaticMode = IS_STATIC;

type WithDate = { date: string };

const isInRange = (date: string, start?: string, end?: string) => {
  const t = new Date(date).getTime();
  if (start && new Date(start).getTime() > t) return false;
  if (end && new Date(end).getTime() < t) return false;
  return true;
};

const filterSeries = <T extends WithDate>(
  data: T[],
  start?: string,
  end?: string
): T[] => {
  if (!start && !end) return data;
  return data.filter((d) => isInRange(d.date, start, end));
};

/** Liquidity regime classification used across GLCI and risk endpoints. */
export type Regime = "tight" | "neutral" | "loose";

export interface DataPoint {
  date: string;
  value: number;
  [key: string]: string | number;
}

export interface SeriesInfo {
  id: string;
  name: string;
  source: string;
  category: string;
  frequency: string;
  unit: string;
}

export interface SeriesResponse {
  id: string;
  name: string;
  source: string;
  unit: string;
  data: DataPoint[];
  latest_date?: string | null;
}

export interface IndexResponse {
  id: string;
  name: string;
  description: string;
  data: DataPoint[];
  latest_date?: string | null;
}

export interface LatestValue {
  id: string;
  date: string;
  value: number;
  change: number;
  unit: string;
}

export interface GLCIPillar {
  name: string;
  value: number;
  weight: number;
  contribution: number;
}

export interface GLCIResponse {
  value: number;
  zscore: number;
  regime: Regime;
  regime_code: number;
  date: string;
  momentum: number;
  prob_regime_change: number;
  pillars: GLCIPillar[];
  data: DataPoint[];
  pillar_data: Record<string, DataPoint[]>;
}

export interface GLCILatest {
  date: string;
  value: number;
  zscore: number;
  regime: number;
  regime_label: string;
  momentum: number;
}

export interface GLCIPillarBreakdown {
  date: string;
  pillars: Record<string, {
    value: number;
    weight: number;
    contribution: number;
  }>;
}

export interface DataFreshnessItem {
  series_id: string;
  pillar: string;
  last_date: string;
  days_old: number;
  is_stale: boolean;
}

export interface GLCITrustResponse {
  as_of: string | null;
  historical_mode: string;
  point_in_time: boolean;
  frequency: string;
  snapshots: {
    count: number;
    first_computed_at: string | null;
    last_computed_at: string | null;
    /** Optional until the richer vintage summary reaches every deployment. */
    unique_signal_dates?: number;
    duplicate_vintages?: number;
    first_signal_date?: string | null;
    latest_signal_date?: string | null;
    latest_signal_revision?: {
      vintage_count: number;
      first_glci: number | null;
      latest_glci: number | null;
      glci_change: number | null;
      glci_min: number | null;
      glci_max: number | null;
      first_zscore: number | null;
      latest_zscore: number | null;
      zscore_change: number | null;
      first_regime: Regime | null;
      latest_regime: Regime | null;
      regime_changed: boolean | null;
    } | null;
  };
  data_quality: {
    loaded_components: number;
    total_components: number;
    missing_components: string[];
    stale_components: string[];
    excluded_components?: string[];
    failed_pillars?: string[];
  };
  pillar_stats: Record<string, unknown>;
}

export interface RegimePeriod {
  regime: string;
  start: string;
  end: string;
}

export interface RegimeHistory {
  periods: RegimePeriod[];
  counts: Record<string, number>;
  current: string | null;
}

// Risk by Regime types
export interface AssetRiskMetrics {
  id: string;
  name: string;
  category: string;
  current_sharpe: number;
  annualized_return: number;
  annualized_volatility: number;
  max_drawdown: number;
  sharpe_by_regime: {
    tight: number | null;
    neutral: number | null;
    loose: number | null;
  };
  return_by_regime: {
    tight: number | null;
    neutral: number | null;
    loose: number | null;
  };
  correlation_with_glci: number | null;
  rolling_sharpe?: DataPoint[];
}

export interface RegimeMatrix {
  assets: string[];
  regimes: string[];
  sharpe_data: (number | null)[][];
  return_data: (number | null)[][];
}

export interface RiskDashboardResponse {
  computed_at: string;
  current_regime: Regime | null;
  assets: AssetRiskMetrics[];
  regime_matrix: RegimeMatrix;
}

// Backtest / Track Record types
export interface BacktestStats {
  median: number | null;
  p25: number | null;
  p75: number | null;
  hit_rate: number | null;
  n: number;
  ci_median_low: number | null;
  ci_median_high: number | null;
  ci_hit_rate_low: number | null;
  ci_hit_rate_high: number | null;
  edge: number | null;
  ci_edge_low: number | null;
  ci_edge_high: number | null;
  edge_standard_error?: number | null;
  /** Normal-approximation p-value from bootstrap standard error, plus adjusted q-value. */
  p_value?: number | null;
  q_value?: number | null;
  /** True only when the edge survives the published FDR procedure. */
  fdr_significant?: boolean | null;
}

export interface BacktestBaseRate {
  median: number | null;
  hit_rate: number | null;
  n: number;
}

export type BacktestHorizon = "4" | "13" | "26";

export interface BacktestAssetResult {
  id: string;
  name: string;
  category: string;
  base_rates: Record<BacktestHorizon, BacktestBaseRate>;
  results: Record<
    string, // classifier: 'glci' | 'nfci'
    Record<
      Regime, // 'tight' | 'neutral' | 'loose'
      Record<BacktestHorizon, BacktestStats>
    >
  >;
}

export interface BacktestTimelineEntry {
  date: string;
  regime: Regime;
  zscore: number | null;
  value: number | null;
}

export interface BacktestClassifierMeta {
  name: string;
  n_per_regime: Partial<Record<Regime, number>>;
  current_regime: Regime | null;
  timeline: BacktestTimelineEntry[];
}

export interface BacktestLiveHorizonStats {
  issued: number;
  matured: number;
  pending: number;
  unavailable: number;
  median: number | null;
  hit_rate: number | null;
  next_maturity_date: string | null;
  status: "collecting" | "reportable";
}

export interface BacktestLiveHorizon extends BacktestLiveHorizonStats {
  by_regime?: Partial<Record<Regime, BacktestLiveHorizonStats>>;
}

export interface BacktestLiveAsset {
  id: string;
  name: string;
  category: string;
  horizons: Record<string, BacktestLiveHorizon>;
}

export interface BacktestLiveEvaluation {
  status: "collecting" | "reportable" | "unavailable";
  methodology: {
    signal_selection: "first_publication_per_signal_date";
    entry_rule: "first_complete_W-FRI_bar_after_computed_at";
    evidence_unit: "asset_horizon_regime";
    source_vintage_complete: false;
    outcome_vintage_complete: false;
    signal_recorded_before_outcome: true;
    min_observations: number;
  };
  ledger: {
    vintage_count: number;
    unique_signal_dates: number;
    duplicate_vintages: number;
    first_signal_date: string | null;
    latest_signal_date: string | null;
  };
  assets: BacktestLiveAsset[];
}

export interface BacktestInference {
  edge_standard_error_method:
    "sample_standard_deviation_of_paired_moving_block_bootstrap_edge_draws";
  p_value_method: "two_sided_normal_approximation_from_bootstrap_standard_error";
  multiple_testing_method: "benjamini_yekutieli";
  multiple_testing_alpha: number;
  multiple_testing_family:
    "all_classifier_asset_regime_horizon_edge_tests_with_finite_p_values";
  tests_in_family: number;
  readiness?: {
    ready: boolean;
    policy: "point_in_time_minimum_history_and_all_regimes";
    classifier: "glci";
    point_in_time_history_required: true;
    point_in_time_history: boolean;
    minimum_classified_weeks: number;
    observed_classified_weeks: number;
    minimum_observations_per_regime: number;
    regime_observations: Record<Regime, number>;
    reasons: string[];
  };
}

export interface BacktestResponse {
  computed_at: string;
  date_range: { start: string; end: string };
  horizons: number[];
  /** Newer payloads publish these fields; optional while static deployments roll forward. */
  frequency?: string;
  entry_lag_weeks?: number;
  historical_mode?: string;
  point_in_time?: boolean;
  regime_threshold_method?: string;
  bootstrap_method?: string;
  bootstrap_iterations?: number;
  min_obs_per_regime?: number;
  inference?: BacktestInference;
  live_evaluation?: BacktestLiveEvaluation;
  classifiers: Record<string, BacktestClassifierMeta>;
  assets: BacktestAssetResult[];
}

// Price leadership (trailing returns relative to each asset's own history)
export interface FlowDestination {
  id: string;
  series_id: string;
  name: string;
  group: string;
  last_date: string;
  ret_4w: number | null;
  ret_13w: number | null;
  ret_26w: number | null;
  /** Current 13w return as a z-score vs the asset's own trailing history. */
  flow_z: number | null;
  glci_corr_52w: number | null;
  spark: DataPoint[];
}

export interface FlowsPair {
  id: string;
  name: string;
  numerator: string;
  denominator: string;
  /** 13w return of the numerator minus the denominator. */
  spread_13w: number | null;
  /** Weekly ratio indexed to 100 at the start of the window. */
  ratio: DataPoint[];
}

export type SectorRotationPhase = "leading" | "weakening" | "improving" | "lagging";
export type SectorFlowConfirmation = "supports" | "diverges" | "neutral";
export type SectorOptionsStatus = "complete" | "partial" | "unavailable" | "disabled";

export interface SectorFundFlow {
  as_of: string;
  aum_usd: number | null;
  flow_1d_usd: number | null;
  flow_5d_usd: number | null;
  flow_20d_usd: number | null;
  flow_5d_pct_aum: number | null;
  flow_20d_pct_aum: number | null;
  flow_20d_z: number | null;
  history_observations: number;
  split_adjustments: number;
}

/** OCC volume is cleared activity only; the source does not identify trade direction. */
export interface SectorOptionsActivity {
  evidence_level: "cleared_activity";
  direction: null;
  trade_side: "unavailable";
  open_close: "unavailable";
  as_of: string;
  week_start: string;
  week_end: string;
  sessions: number;
  call_volume: number;
  put_volume: number;
  total_volume: number;
  put_call_ratio: number | null;
  prior_month_daily_average: number | null;
  activity_ratio: number | null;
  excluded_adjusted_roots: string[];
}

export interface SectorRotationRow {
  id: string;
  ticker: string;
  name: string;
  rank: number;
  price_as_of: string;
  return_21d: number | null;
  return_63d: number | null;
  return_126d: number | null;
  excess_21d: number | null;
  excess_63d: number | null;
  excess_126d: number | null;
  relative_strength: number | null;
  acceleration: number | null;
  absolute_trend: number | null;
  above_200d: boolean;
  phase: SectorRotationPhase;
  price_score: number | null;
  fund_flow: SectorFundFlow;
  options_activity: SectorOptionsActivity | null;
  flow_confirmation: SectorFlowConfirmation;
}

export interface SectorRotationResponse {
  schema_version: string;
  computed_at: string;
  status: "complete" | "partial" | "unavailable";
  signal_status: "descriptive_not_backtested";
  universe: "select_sector_spdr_11";
  benchmark: string;
  price_as_of: string;
  fund_flow_as_of: string;
  options_as_of: string | null;
  price_basis: "yahoo_adjusted_close";
  coverage: {
    expected_sectors: number;
    price: number;
    fund_flows: number;
    options: number;
    complete_price_universe: boolean;
    complete_fund_flow_universe: boolean;
    options_status: SectorOptionsStatus;
    options_errors: Record<string, string>;
  };
  methodology: {
    price_score: string;
    phase: string;
    fund_flow: string;
    flow_z: string;
    options: string;
    score_inputs: string[];
    excluded_from_score: string[];
  };
  sources: {
    fund_flows: {
      provider: string;
      url_template: string;
      point_in_time_history: boolean;
      revision_policy: string;
    };
    prices: {
      provider: string;
      basis: string;
      point_in_time_history: boolean;
    };
    options: {
      provider: string;
      url: string;
      documentation: string;
      evidence_level: "cleared_activity";
      trade_direction: "unavailable";
      open_close: "unavailable";
      standard_roots_only: boolean;
      baseline_month: string | null;
    };
  };
  opportunities: {
    leaders: string[];
    laggards: string[];
    improving: string[];
    strongest_inflows: string[];
    most_active_options: string[];
  };
  sectors: SectorRotationRow[];
}

export interface FlowsResponse {
  computed_at: string;
  as_of: string;
  flow_window_weeks: number;
  flow_history_weeks: number;
  glci_corr_window_weeks: number;
  destinations: FlowDestination[];
  pair: FlowsPair | null;
  /** Optional while static deployments roll forward to the sector-rotation schema. */
  sector_rotation?: SectorRotationResponse | null;
}

class ApiClient {
  private baseUrl: string;
  private isStatic: boolean;

  constructor(baseUrl: string = API_BASE_URL, isStatic: boolean = IS_STATIC) {
    this.baseUrl = baseUrl;
    this.isStatic = isStatic;
  }

  private buildUrl(endpoint: string): string {
    if (!this.isStatic) {
      return `${this.baseUrl}${endpoint}`;
    }
    // Strip query params; static JSON is full history and we filter client-side.
    const [path] = endpoint.split("?");
    const clean = path.replace(/\/+$/, "");
    return `${this.baseUrl}${clean}/index.json`;
  }

  private async fetch<T>(endpoint: string): Promise<T> {
    const url = this.buildUrl(endpoint);
    // GitHub Pages serves the JSON with max-age=600, which lets a browser
    // show pre-publish data for up to 10 minutes after the pipeline runs.
    // "no-cache" keeps the cached copy but revalidates it (ETag/304), so a
    // reload always reflects the latest publish.
    const response = await fetch(url, { cache: "no-cache" });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  async listSeries(): Promise<SeriesInfo[]> {
    return this.fetch<SeriesInfo[]>("/api/series");
  }

  async getSeries(
    seriesId: string,
    start?: string,
    end?: string
  ): Promise<SeriesResponse> {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString() ? `?${params.toString()}` : "";
    const result = await this.fetch<SeriesResponse>(`/api/series/${seriesId}${query}`);
    result.latest_date = result.latest_date ?? result.data[result.data.length - 1]?.date ?? null;
    if (this.isStatic) {
      result.data = filterSeries(result.data, start, end);
    }
    return result;
  }

  async getSeriesLatest(seriesId: string): Promise<LatestValue> {
    return this.fetch<LatestValue>(`/api/series/${seriesId}/latest`);
  }

  async listIndices(): Promise<{ id: string; name: string; description: string }[]> {
    return this.fetch("/api/indices");
  }

  async getIndex(
    indexId: string,
    start?: string,
    end?: string
  ): Promise<IndexResponse> {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString() ? `?${params.toString()}` : "";
    const result = await this.fetch<IndexResponse>(`/api/indices/${indexId}${query}`);
    result.latest_date = result.latest_date ?? result.data[result.data.length - 1]?.date ?? null;
    if (this.isStatic) {
      result.data = filterSeries(result.data, start, end);
    }
    return result;
  }

  async getMultipleSeries(
    seriesIds: string[],
    start?: string,
    end?: string
  ): Promise<Record<string, SeriesResponse>> {
    const results: Record<string, SeriesResponse> = {};
    await Promise.all(
      seriesIds.map(async (id) => {
        try {
          results[id] = await this.getSeries(id, start, end);
        } catch (e) {
          console.error(`Failed to fetch ${id}:`, e);
        }
      })
    );
    return results;
  }

  async getGLCI(start?: string, end?: string): Promise<GLCIResponse> {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString() ? `?${params.toString()}` : "";
    const result = await this.fetch<GLCIResponse>(`/api/glci${query}`);
    if (this.isStatic) {
      result.data = filterSeries(result.data, start, end);
      const filteredPillarData: Record<string, DataPoint[]> = {};
      for (const [pillar, series] of Object.entries(result.pillar_data || {})) {
        filteredPillarData[pillar] = filterSeries(series, start, end);
      }
      result.pillar_data = filteredPillarData;
    }
    return result;
  }

  async getGLCILatest(): Promise<GLCILatest> {
    return this.fetch<GLCILatest>("/api/glci/latest");
  }

  async getGLCIPillars(): Promise<GLCIPillarBreakdown> {
    return this.fetch<GLCIPillarBreakdown>("/api/glci/pillars");
  }

  async getGLCIFreshness(): Promise<DataFreshnessItem[]> {
    return this.fetch<DataFreshnessItem[]>("/api/glci/freshness");
  }

  async getGLCITrust(): Promise<GLCITrustResponse> {
    return this.fetch<GLCITrustResponse>("/api/glci/trust");
  }

  async getRegimeHistory(start?: string, end?: string): Promise<RegimeHistory> {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.fetch<RegimeHistory>(`/api/glci/regime-history${query}`);
  }

  // Risk by Regime endpoints
  async getRiskMetrics(): Promise<RiskDashboardResponse> {
    return this.fetch<RiskDashboardResponse>("/api/risk");
  }

  async getBacktest(): Promise<BacktestResponse> {
    return this.fetch<BacktestResponse>("/api/backtest/track_record");
  }

  async getFlows(): Promise<FlowsResponse> {
    return this.fetch<FlowsResponse>("/api/flows");
  }

}

const api = new ApiClient();
export default api;
