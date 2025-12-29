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
}

export interface IndexResponse {
  id: string;
  name: string;
  description: string;
  data: DataPoint[];
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
  regime: "tight" | "neutral" | "loose";
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
  current_regime: "tight" | "neutral" | "loose";
  assets: AssetRiskMetrics[];
  regime_matrix: RegimeMatrix;
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
    const response = await fetch(url);
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

  async getAssetRisk(assetId: string): Promise<AssetRiskMetrics> {
    return this.fetch<AssetRiskMetrics>(`/api/risk/${assetId}`);
  }
}

export const api = new ApiClient();
export default api;
