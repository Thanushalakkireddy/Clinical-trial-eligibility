import { useState, useEffect, useCallback } from 'react';
import { HealthResponse } from '../types';
import { getHealthStatus } from '../services/api';

export function useHealth() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getHealthStatus();
      setData(result);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unable to connect to backend';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return { data, loading, error, refetch: checkHealth };
}
