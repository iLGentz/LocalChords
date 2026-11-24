import { useEffect } from "react";

import type { Player } from "@/hooks/usePlayer";

interface Options {
  player: Player | null;
  selected: string | null;
  onSelect: (id: string) => void;
  downbeats: number[];
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * Spazio play/pausa, ←/→ ±5 s (Maiusc: battuta precedente/successiva), 1-6 seleziona la
 * traccia, M mute, S solo, L attiva/disattiva il loop (se non c'è, ripete la battuta corrente).
 * Ignorate mentre si scrive in un campo; lo spazio su un pulsante lo attiva come di norma.
 */
export function usePlayerShortcuts({ player, selected, onSelect, downbeats }: Options): void {
  useEffect(() => {
    if (!player) return;
    const { engine } = player;
    const onKey = (e: KeyboardEvent): void => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return;
      const snap = engine.getSnapshot();
      const t = engine.getTime();
      const key = e.key.toLowerCase();
      if (e.key === " ") {
        if (e.target instanceof HTMLButtonElement) return;
        e.preventDefault();
        engine.toggle();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const forward = e.key === "ArrowRight";
        if (e.shiftKey && downbeats.length > 0) {
          const target = forward
            ? downbeats.find((d) => d > t + 0.05)
            : [...downbeats].reverse().find((d) => d < t - 0.3);
          engine.seek(target ?? (forward ? snap.duration : 0));
        } else {
          engine.seek(t + (forward ? 5 : -5));
        }
      } else if (/^[1-9]$/.test(key)) {
        const track = snap.tracks[Number(key) - 1];
        if (track) onSelect(track.id);
      } else if (key === "m" || key === "s") {
        const track = snap.tracks.find((tr) => tr.id === selected) ?? snap.tracks[0];
        if (!track) return;
        if (key === "m") engine.setTrack(track.id, { muted: !track.muted });
        else engine.setTrack(track.id, { solo: !track.solo });
      } else if (key === "l") {
        if (snap.loop) {
          engine.setLoop({ ...snap.loop, enabled: !snap.loop.enabled });
        } else if (downbeats.length > 1) {
          const start = [...downbeats].reverse().find((d) => d <= t) ?? downbeats[0] ?? 0;
          const end = downbeats.find((d) => d > start + 0.05) ?? snap.duration;
          engine.setLoop({ a: start, b: end, enabled: true });
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [player, selected, onSelect, downbeats]);
}
