import { useEffect, useState } from "react";

import { apiGet, asApiError, type Analysis, type ApiError, type WaveformPeaks } from "@/lib/api";

export type AnalysisState =
  | { kind: "loading" }
  | { kind: "ready"; analysis: Analysis; waveform: WaveformPeaks | null }
  | { kind: "error"; error: ApiError };

/** Carica analisi e waveform di un brano; si ricarica quando cambia `version`. */
export function useAnalysis(songId: string, version: string): AnalysisState {
  const [state, setState] = useState<AnalysisState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    Promise.all([
      apiGet<Analysis>(`/songs/${songId}/analysis`, controller.signal),
      apiGet<WaveformPeaks>(`/songs/${songId}/waveform`, controller.signal).catch(() => null),
    ])
      .then(([analysis, waveform]) => setState({ kind: "ready", analysis, waveform }))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setState({ kind: "error", error: asApiError(err) });
      });
    return () => controller.abort();
  }, [songId, version]);

  return state;
}
