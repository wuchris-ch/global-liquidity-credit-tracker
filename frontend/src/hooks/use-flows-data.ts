/**
 * Hook to fetch the liquidity-flows payload (where the marginal dollar goes).
 */
import { useCallback, useEffect, useState } from "react";
import api, { FlowsResponse } from "@/lib/api";

export interface UseFlowsDataResult {
  data: FlowsResponse | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useFlowsData(): UseFlowsDataResult {
  const [data, setData] = useState<FlowsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.getFlows();
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
