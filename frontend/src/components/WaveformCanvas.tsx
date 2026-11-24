import { useEffect, useRef, useState, type PointerEvent } from "react";

import { snapToBeat, type LoopState } from "@/audio/engine";
import type { SectionInfo, WaveformPeaks } from "@/lib/api";

interface WaveformCanvasProps {
  peaks: WaveformPeaks;
  duration: number;
  sections: SectionInfo[];
  beats: number[];
  time: number;
  loop: LoopState | null;
  snap: boolean;
  onSeek: (t: number) => void;
  onLoop: (loop: LoopState) => void;
}

const HEIGHT = 112;
const BAND = 18;

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/**
 * Waveform dai picchi precalcolati, con sezioni, loop e cursore.
 * Clic: sposta. Trascina: crea il loop A/B (agganciato ai beat se attivo).
 * Banda delle sezioni: clic sposta all'inizio, Maiusc+clic mette in loop la sezione.
 */
export function WaveformCanvas(props: WaveformCanvasProps) {
  const { peaks, duration, sections, beats, time, loop, snap, onSeek, onLoop } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(800);
  const [drag, setDrag] = useState<{ from: number; to: number; moved: boolean } | null>(null);

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(200, Math.floor(entry.contentRect.width)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || duration <= 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = HEIGHT * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, HEIGHT);
    const x = (t: number): number => (t / duration) * width;

    // sezioni: banda in alto e velatura leggera
    ctx.font = "11px 'Segoe UI', system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (const s of sections) {
      const x0 = x(s.start_s);
      const x1 = x(s.end_s);
      ctx.fillStyle = `${s.color}33`;
      ctx.fillRect(x0, 0, x1 - x0, BAND);
      ctx.fillStyle = `${s.color}12`;
      ctx.fillRect(x0, BAND, x1 - x0, HEIGHT - BAND);
      ctx.fillStyle = s.color;
      ctx.fillRect(x0, 0, 2, BAND);
      ctx.fillStyle = cssVar("--color-ink-muted", "#a8a097");
      ctx.save();
      ctx.beginPath();
      ctx.rect(x0, 0, x1 - x0 - 2, BAND);
      ctx.clip();
      ctx.fillText(s.name, x0 + 5, BAND / 2);
      ctx.restore();
    }

    // loop
    const shownLoop = drag?.moved ? { a: Math.min(drag.from, drag.to), b: Math.max(drag.from, drag.to), enabled: true } : loop;
    if (shownLoop) {
      ctx.fillStyle = shownLoop.enabled ? "rgba(240,167,58,0.16)" : "rgba(168,160,151,0.10)";
      ctx.fillRect(x(shownLoop.a), BAND, x(shownLoop.b) - x(shownLoop.a), HEIGHT - BAND);
      ctx.fillStyle = shownLoop.enabled ? cssVar("--color-accent", "#f0a73a") : "#77716a";
      ctx.fillRect(x(shownLoop.a), BAND, 1.5, HEIGHT - BAND);
      ctx.fillRect(x(shownLoop.b) - 1.5, BAND, 1.5, HEIGHT - BAND);
    }

    // waveform (una barra ogni 3 px)
    const mid = BAND + (HEIGHT - BAND) / 2;
    const amp = (HEIGHT - BAND) / 2 - 4;
    const step = 3;
    const values = peaks.peaks;
    const played = x(time);
    for (let px = 0; px < width; px += step) {
      const i0 = Math.floor((px / width) * values.length);
      const i1 = Math.max(i0 + 1, Math.floor(((px + step) / width) * values.length));
      let v = 0;
      for (let i = i0; i < i1 && i < values.length; i++) v = Math.max(v, values[i] ?? 0);
      const h = Math.max(1, v * amp);
      ctx.fillStyle = px < played ? "#b9b1a6" : "#5b554e";
      ctx.fillRect(px, mid - h, step - 1, h * 2);
    }

    // cursore
    ctx.fillStyle = cssVar("--color-accent", "#f0a73a");
    ctx.fillRect(played - 1, 0, 2, HEIGHT);
  }, [width, peaks, duration, sections, time, loop, drag]);

  const timeAt = (e: PointerEvent<HTMLCanvasElement>): number => {
    const rect = e.currentTarget.getBoundingClientRect();
    return Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1) * duration;
  };
  const snapped = (t: number): number => (snap ? snapToBeat(t, beats) : t);

  const onPointerDown = (e: PointerEvent<HTMLCanvasElement>): void => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = timeAt(e);
    if (e.clientY - rect.top < BAND) {
      const section = sections.find((s) => t >= s.start_s && t < s.end_s);
      if (section) {
        if (e.shiftKey) onLoop({ a: section.start_s, b: section.end_s, enabled: true });
        else onSeek(section.start_s);
      }
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag({ from: t, to: t, moved: false });
  };

  const onPointerMove = (e: PointerEvent<HTMLCanvasElement>): void => {
    if (!drag) return;
    const t = timeAt(e);
    const moved = drag.moved || Math.abs(t - drag.from) / duration > 0.004;
    setDrag({ ...drag, to: t, moved });
  };

  const onPointerUp = (): void => {
    if (!drag) return;
    if (drag.moved) {
      const a = snapped(Math.min(drag.from, drag.to));
      const b = snapped(Math.max(drag.from, drag.to));
      if (b - a > 0.2) onLoop({ a, b, enabled: true });
    } else {
      onSeek(drag.from);
    }
    setDrag(null);
  };

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="Waveform del brano. Clic per spostarsi, trascina per creare un loop, Maiusc+clic su una sezione per ripeterla."
      style={{ width: "100%", height: HEIGHT }}
      className="cursor-pointer touch-none rounded-md bg-ground"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => setDrag(null)}
    />
  );
}
