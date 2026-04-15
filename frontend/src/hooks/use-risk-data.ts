/**
 * React hooks for fetching risk metrics data.
 */
import { useState, useEffect, useCallback } from "react";
import api, { RiskDashboardResponse } from "@/lib/api";

export interface UseRiskDataResult {
  data: RiskDashboardResponse | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch the risk dashboard data including all asset metrics
 * and regime-conditional performance.
 */
export function useRiskData(): UseRiskDataResult {
  const [data, setData] = useState<RiskDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.getRiskMetrics();
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

