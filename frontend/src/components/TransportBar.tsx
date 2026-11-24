import { RATE_MAX, RATE_MIN, SEMITONES_MAX, snapToBeat } from "@/audio/engine";
import { Button } from "@/components/ui";
import type { Player } from "@/hooks/usePlayer";
import { formatDuration } from "@/lib/format";

interface TransportBarProps {
  player: Player;
  time: number;
  beats: number[];
  snap: boolean;
  onSnapChange: (v: boolean) => void;
  hasBpm: boolean;
}

function fmt(t: number): string {
  const base = formatDuration(t);
  return `${base}.${Math.floor((t % 1) * 10)}`;
}

/** Barra di trasporto fissa in basso: play, velocità, tonalità, loop, metronomo, volume. */
export function TransportBar({ player, time, beats, snap, onSnapChange, hasBpm }: TransportBarProps) {
  const { engine, snap: s } = player;
  const loading = s.status === "loading";
  const playing = s.status === "playing";
  const loop = s.loop;
  const pointAt = (t: number): number => (snap ? snapToBeat(t, beats) : t);

  const setA = (): void => {
    const a = pointAt(time);
    const b = loop && loop.b > a + 0.2 ? loop.b : Math.min(a + 8, s.duration);
    engine.setLoop({ a, b, enabled: true });
  };
  const setB = (): void => {
    const b = pointAt(time);
    const a = loop && loop.a < b - 0.2 ? loop.a : Math.max(b - 8, 0);
    engine.setLoop({ a, b, enabled: true });
  };

  return (
    <div
      role="region"
      aria-label="Trasporto"
      className="sticky bottom-0 z-10 -mx-8 mt-6 border-t border-line bg-surface/95 px-6 py-2.5 backdrop-blur"
    >
      {s.status === "error" && <p className="mb-1 text-xs text-bad">{s.error}</p>}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            className="w-24"
            disabled={loading || s.status === "error"}
            onClick={() => engine.toggle()}
            aria-keyshortcuts="Space"
          >
            {loading ? `${Math.round(s.loadProgress * 100)}%` : playing ? "❚❚ Pausa" : "▶ Play"}
          </Button>
          <Button variant="ghost" onClick={() => engine.stop()} disabled={loading} title="Stop">
            ■
          </Button>
          <span className="w-28 font-mono text-sm tabular-nums" aria-live="off">
            {fmt(time)} <span className="text-ink-muted">/ {formatDuration(s.duration)}</span>
          </span>
          {s.countingIn && <span className="font-semibold text-accent">Count-in…</span>}
        </div>

        <label className="flex items-center gap-2">
          <span className="text-ink-muted">Velocità</span>
          <input
            type="range"
            min={RATE_MIN}
            max={RATE_MAX}
            step={0.05}
            value={s.rate}
            onChange={(e) => engine.setRate(Number(e.target.value))}
            className="w-24 accent-[var(--color-accent)]"
          />
          <button type="button" className="w-12 font-mono" title="Torna a 1×" onClick={() => engine.setRate(1)}>
            {s.rate.toFixed(2)}×
          </button>
        </label>

        <div className="flex items-center gap-1" title={s.pitchAvailable ? undefined : "Cambio di tonalità non disponibile"}>
          <span className="text-ink-muted">Tonalità</span>
          <Button variant="ghost" className="px-2 py-0.5" disabled={!s.pitchAvailable || s.semitones <= -SEMITONES_MAX} onClick={() => engine.setSemitones(s.semitones - 1)} aria-label="Un semitono sotto">
            −
          </Button>
          <button type="button" className="w-8 text-center font-mono" title="Torna alla tonalità originale" onClick={() => engine.setSemitones(0)}>
            {s.semitones > 0 ? `+${s.semitones}` : s.semitones}
          </button>
          <Button variant="ghost" className="px-2 py-0.5" disabled={!s.pitchAvailable || s.semitones >= SEMITONES_MAX} onClick={() => engine.setSemitones(s.semitones + 1)} aria-label="Un semitono sopra">
            +
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant={loop?.enabled ? "secondary" : "ghost"}
            className={`px-2 py-0.5 ${loop?.enabled ? "border-accent text-accent" : ""}`}
            disabled={!loop}
            aria-pressed={loop?.enabled ?? false}
            aria-keyshortcuts="L"
            onClick={() => loop && engine.setLoop({ ...loop, enabled: !loop.enabled })}
          >
            Loop
          </Button>
          <Button variant="ghost" className="px-2 py-0.5" onClick={setA} title="Inizio del loop alla posizione attuale">
            A
          </Button>
          <Button variant="ghost" className="px-2 py-0.5" onClick={setB} title="Fine del loop alla posizione attuale">
            B
          </Button>
          {loop && (
            <span className="font-mono text-ink-muted">
              {formatDuration(loop.a)}–{formatDuration(loop.b)}
            </span>
          )}
          {loop && (
            <Button variant="ghost" className="px-1.5 py-0.5" onClick={() => engine.setLoop(null)} aria-label="Rimuovi il loop">
              ✕
            </Button>
          )}
          <label className="ml-1 flex items-center gap-1 text-ink-muted" title="Aggancia A e B al beat più vicino">
            <input type="checkbox" checked={snap} onChange={(e) => onSnapChange(e.target.checked)} className="accent-[var(--color-accent)]" />
            snap
          </label>
        </div>

        <div className="flex items-center gap-2" title={hasBpm ? undefined : "Serve la beat grid dell'analisi"}>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={s.metronome.enabled}
              disabled={!hasBpm}
              onChange={(e) => engine.setMetronome({ enabled: e.target.checked })}
              className="accent-[var(--color-accent)]"
            />
            Metronomo
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={s.metronome.volume}
            aria-label="Volume del metronomo"
            onChange={(e) => engine.setMetronome({ volume: Number(e.target.value) })}
            className="w-16 accent-[var(--color-accent)]"
          />
          <label className="flex items-center gap-1">
            <span className="text-ink-muted">Count-in</span>
            <select
              value={s.countInBars}
              disabled={!hasBpm}
              onChange={(e) => engine.setCountIn(Number(e.target.value) as 0 | 1 | 2 | 4)}
              className="rounded border border-line bg-ground px-1 py-0.5"
            >
              <option value={0}>no</option>
              <option value={1}>1 batt.</option>
              <option value={2}>2 batt.</option>
              <option value={4}>4 batt.</option>
            </select>
          </label>
        </div>

        <label className="ml-auto flex items-center gap-2">
          <span className="text-ink-muted">Volume</span>
          <input
            type="range"
            min={0}
            max={1.5}
            step={0.01}
            value={s.masterVolume}
            onChange={(e) => engine.setMasterVolume(Number(e.target.value))}
            className="w-20 accent-[var(--color-accent)]"
          />
          <span
            role="status"
            aria-label={s.clipping ? "Clipping: abbassa il volume" : "Nessun clipping"}
            title={s.clipping ? "Clipping: abbassa il volume o gli stem" : "Nessun clipping"}
            className={`size-2.5 rounded-full ${s.clipping ? "bg-bad" : "bg-raised"}`}
          />
        </label>
      </div>
    </div>
  );
}
