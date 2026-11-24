import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, apiGet, asApiError, isJobActive, type Song } from "@/lib/api";

const FAST_MS = 1000;
const SLOW_MS = 10000;

export interface SongsState {
  songs: Song[];
  loading: boolean;
  error: ApiError | null;
  refresh: () => void;
}

/** Catalogo con ricerca. Aggiorna ogni secondo mentre ci sono importazioni in corso. */
export function useSongs(query: string): SongsState {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    const path = query.trim() ? `/songs?q=${encodeURIComponent(query.trim())}` : "/songs";
    const delay = query === "" ? 0 : 200; // piccolo debounce sulla ricerca

    const load = async (): Promise<void> => {
      let next = SLOW_MS;
      try {
        const data = await apiGet<Song[]>(path, controller.signal);
        setSongs(data);
        setError(null);
        if (data.some((s) => isJobActive(s.job))) next = FAST_MS;
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(asApiError(err));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
      if (!controller.signal.aborted) timer.current = window.setTimeout(() => void load(), next);
    };

    timer.current = window.setTimeout(() => void load(), delay);
    return () => {
      controller.abort();
      window.clearTimeout(timer.current);
    };
  }, [query, tick]);

  return { songs, loading, error, refresh };
}
