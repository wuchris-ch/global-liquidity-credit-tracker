/**
 * Hook to fetch the GLCI backtest / track record payload.
 */
import { useCallback, useEffect, useState } from "react";
import api, { BacktestResponse } from "@/lib/api";

export interface UseBacktestDataResult {
  data: BacktestResponse | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useBacktestData(): UseBacktestDataResult {
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.getBacktest();
      setData(response);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}
