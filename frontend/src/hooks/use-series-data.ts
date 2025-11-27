/**
 * React hooks for fetching series and index data.
 */
import { useState, useEffect, useCallback } from "react";
import api, { DataPoint, SeriesInfo, SeriesResponse, IndexResponse } from "@/lib/api";

export interface UseSeriesDataOptions {
  start?: string;
  end?: string;
  enabled?: boolean;
}

export interface UseSeriesDataResult {
  data: DataPoint[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useSeriesData(
  seriesId: string | null,
  options: UseSeriesDataOptions = {}
): UseSeriesDataResult {
  const { start, end, enabled = true } = options;
  const [data, setData] = useState<DataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    if (!seriesId || !enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.getSeries(seriesId, start, end);
      setData(response.data);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, [seriesId, start, end, enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}

export function useIndexData(
  indexId: string | null,
  options: UseSeriesDataOptions = {}
): UseSeriesDataResult {
  const { start, end, enabled = true } = options;
  const [data, setData] = useState<DataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    if (!indexId || !enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.getIndex(indexId, start, end);
      setData(response.data);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, [indexId, start, end, enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}

export interface UseMultipleSeriesResult {
  data: Record<string, DataPoint[]>;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useMultipleSeries(
  seriesIds: string[],
  options: UseSeriesDataOptions = {}
): UseMultipleSeriesResult {
  const { start, end, enabled = true } = options;
  const [data, setData] = useState<Record<string, DataPoint[]>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    if (seriesIds.length === 0 || !enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      const responses = await api.getMultipleSeries(seriesIds, start, end);
      const result: Record<string, DataPoint[]> = {};
      for (const [id, response] of Object.entries(responses)) {
        result[id] = response.data;
      }
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setIsLoading(false);
    }
  }, [seriesIds.join(","), start, end, enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}

export interface UseSeriesListResult {
  series: SeriesInfo[];
  isLoading: boolean;
  error: Error | null;
}

export function useSeriesList(): UseSeriesListResult {
  const [series, setSeries] = useState<SeriesInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    api
      .listSeries()
      .then(setSeries)
      .catch((e) => setError(e instanceof Error ? e : new Error(String(e))))
      .finally(() => setIsLoading(false));
  }, []);

  return { series, isLoading, error };
}
