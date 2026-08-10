import { createContext, useCallback, useContext, useEffect, useState } from "react";

export const SyncContext = createContext<{
  refreshKey: number;
  bump: () => void;
}>({ refreshKey: 0, bump: () => {} });

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const { refreshKey } = useContext(SyncContext);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const retry = useCallback(() => setRetryKey((k) => k + 1), []);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(path)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as T;
      })
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, refreshKey, retryKey, ...deps]);

  return { data, loading, error, retry };
}
