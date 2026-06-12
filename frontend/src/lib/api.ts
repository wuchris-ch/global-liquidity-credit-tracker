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

export interface RegimePeriod {
  regime: string;
  start: string;
  end: string;
}

export interface RegimeHistory {
  periods: RegimePeriod[];
  counts: Record<string, number>;
  current: string;
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
  correlation_with_glci: number;
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
  current_regime: Regime;
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

export interface BacktestResponse {
  computed_at: string;
  date_range: { start: string; end: string };
  horizons: number[];
  classifiers: Record<string, BacktestClassifierMeta>;
  assets: BacktestAssetResult[];
}

// Liquidity flows (where the marginal dollar is going)
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

export interface FlowsResponse {
  computed_at: string;
  as_of: string;
  flow_window_weeks: number;
  flow_history_weeks: number;
  glci_corr_window_weeks: number;
  destinations: FlowDestination[];
  pair: FlowsPair | null;
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
