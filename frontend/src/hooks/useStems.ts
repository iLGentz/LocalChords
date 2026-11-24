import { useEffect, useState } from "react";

import { apiGet, type StemInfo } from "@/lib/api";

/** Stem del brano (null mentre carica); si ricarica quando cambia `version`. */
export function useStems(songId: string, version: string): StemInfo[] | null {
  const [stems, setStems] = useState<StemInfo[] | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setStems(null);
    apiGet<StemInfo[]>(`/songs/${songId}/stems`, controller.signal)
      .then(setStems)
      .catch(() => {
        if (!controller.signal.aborted) setStems([]);
      });
    return () => controller.abort();
  }, [songId, version]);
  return stems;
}
