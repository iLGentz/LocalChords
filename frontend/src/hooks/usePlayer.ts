import { useEffect, useState, useSyncExternalStore } from "react";

import { PlayerEngine, type BeatGrid, type PlayerSnapshot, type TrackSpec } from "@/audio/engine";

export interface Player {
  engine: PlayerEngine;
  snap: PlayerSnapshot;
}

const noopSubscribe = (): (() => void) => () => undefined;
const noSnapshot = (): null => null;

/** Un motore per insieme di tracce: cambiare tracce (es. stem appena creati) lo ricrea. */
export function usePlayer(tracks: TrackSpec[], grid: BeatGrid | null): Player | null {
  const key = tracks.map((t) => t.url).join("|");
  const [engine, setEngine] = useState<PlayerEngine | null>(null);

  useEffect(() => {
    if (!key) return;
    const e = new PlayerEngine();
    setEngine(e);
    void e.load(tracks);
    return () => {
      e.dispose();
      setEngine(null);
    };
  }, [key]); // `tracks` è descritto completamente da `key`

  useEffect(() => {
    if (engine && grid) engine.setBeatGrid(grid);
  }, [engine, grid]);

  const snap = useSyncExternalStore<PlayerSnapshot | null>(
    engine ? engine.subscribe : noopSubscribe,
    engine ? engine.getSnapshot : noSnapshot,
  );
  return engine && snap ? { engine, snap } : null;
}

/** Posizione di ascolto, aggiornata a ogni frame mentre suona. */
export function usePlayerTime(player: Player | null): number {
  const [time, setTime] = useState(0);
  const engine = player?.engine ?? null;
  const snap = player?.snap ?? null;

  useEffect(() => {
    if (!engine) return;
    let frame = 0;
    const tick = (): void => {
      setTime(engine.getTime());
      if (engine.isPlaying) frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [engine, snap]);

  return time;
}
