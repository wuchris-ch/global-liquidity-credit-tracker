/**
 * Optional trust metadata for the GLCI. The Today page remains usable while
 * older static deployments catch up with this endpoint.
 */
import { useCallback, useEffect, useState } from "react";
import api, { type GLCITrustResponse } from "@/lib/api";

export interface UseGLCITrustResult {
  data: GLCITrustResponse | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useGLCITrust(): UseGLCITrustResult {
  const [data, setData] = useState<GLCITrustResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setData(await api.getGLCITrust());
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
