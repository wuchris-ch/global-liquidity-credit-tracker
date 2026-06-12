/**
 * Hook to fetch the full GLCI regime history (periods + counts + current).
 */
import { useState, useEffect, useCallback } from "react";
import api, { RegimeHistory } from "@/lib/api";

export interface UseRegimeHistoryResult {
  data: RegimeHistory | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useRegimeHistory(): UseRegimeHistoryResult {
  const [data, setData] = useState<RegimeHistory | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.getRegimeHistory();
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
