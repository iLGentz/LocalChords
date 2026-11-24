import { useEffect, useState } from "react";

import { ApiError, apiGet, type Health } from "@/lib/api";

const POLL_MS = 5000;

export type HealthState =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; error: ApiError };

/** Interroga `/api/health` periodicamente. */
export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let timer: number | undefined;
    const controller = new AbortController();

    const load = async (): Promise<void> => {
      try {
        const health = await apiGet<Health>("/health", controller.signal);
        setState({ kind: "ok", health });
      } catch (err) {
        if (controller.signal.aborted) return;
        setState({
          kind: "error",
          error:
            err instanceof ApiError
              ? err
              : new ApiError(0, { code: "unknown", message: String(err), detail: null }),
        });
      }
      timer = window.setTimeout(() => void load(), POLL_MS);
    };

    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);

  return state;
}
