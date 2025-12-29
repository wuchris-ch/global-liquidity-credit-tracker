/**
 * React hooks for fetching risk metrics data.
 */
import { useState, useEffect, useCallback } from "react";
import api, { RiskDashboardResponse, AssetRiskMetrics } from "@/lib/api";

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

export interface UseAssetRiskResult {
  data: AssetRiskMetrics | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch risk metrics for a single asset.
 */
export function useAssetRisk(assetId: string | null): UseAssetRiskResult {
  const [data, setData] = useState<AssetRiskMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    if (!assetId) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.getAssetRisk(assetId);
      setData(response);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}
