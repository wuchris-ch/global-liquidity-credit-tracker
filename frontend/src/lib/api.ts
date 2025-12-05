/**
 * API client for fetching data from the Python backend.
 */

// Allows pointing the frontend to static JSON (e.g., Cloudflare R2) first,
// then falling back to a live API (dev/local).
const API_BASE_URL =
  (process.env.NEXT_PUBLIC_DATA_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000").replace(/\/$/, "");

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

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`);
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
    return this.fetch<SeriesResponse>(`/api/series/${seriesId}${query}`);
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
    return this.fetch<IndexResponse>(`/api/indices/${indexId}${query}`);
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
    return this.fetch<GLCIResponse>(`/api/glci${query}`);
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
}

export const api = new ApiClient();
export default api;
