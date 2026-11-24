import { Button } from "@/components/ui";
import type { Player } from "@/hooks/usePlayer";

interface MixerPanelProps {
  player: Player;
  selected: string | null;
  onSelect: (id: string) => void;
  hasStems: boolean;
}

/** Volume, mute e solo per stem, con misuratore e spia di clipping. */
export function MixerPanel({ player, selected, onSelect, hasStems }: MixerPanelProps) {
  const { engine, snap } = player;
  const vocals = snap.tracks.find((t) => t.id === "vocals");

  return (
    <section aria-labelledby="mixer-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="mixer-title" className="text-base font-semibold">
          Mixer
        </h2>
        {vocals && (
          <div className="flex gap-1">
            <Button variant="ghost" className="px-2 py-0.5 text-xs" onClick={() => engine.soloOnly("vocals")}>
              Solo voce
            </Button>
            <Button variant="ghost" className="px-2 py-0.5 text-xs" onClick={() => engine.muteOnly("vocals")}>
              Solo base
            </Button>
            <Button variant="ghost" className="px-2 py-0.5 text-xs" onClick={() => engine.muteOnly(null)}>
              Tutti
            </Button>
          </div>
        )}
      </div>
      {!hasStems && (
        <p className="mb-2 text-xs text-ink-muted">
          Mix completo: separa il brano in stem (qui sotto) per regolare voce e strumenti.
        </p>
      )}
      <ul className="flex flex-col gap-1.5">
        {snap.tracks.map((t, i) => (
          <li
            key={t.id}
            className={`grid grid-cols-[5.5rem_auto_auto_minmax(0,1fr)_2.5rem] items-center gap-2 rounded-md px-2 py-1 ${selected === t.id ? "bg-raised" : ""}`}
          >
            <button
              type="button"
              onClick={() => onSelect(t.id)}
              aria-pressed={selected === t.id}
              title={`Seleziona (tasto ${i + 1}); M e S agiscono sulla traccia selezionata`}
              className="truncate text-left"
            >
              <span className="mr-1 font-mono text-xs text-ink-muted">{i + 1}</span>
              {t.label}
            </button>
            <button
              type="button"
              aria-pressed={t.muted}
              onClick={() => engine.setTrack(t.id, { muted: !t.muted })}
              className={`w-7 rounded border text-xs font-semibold ${t.muted ? "border-bad bg-bad/20 text-bad" : "border-line text-ink-muted"}`}
              aria-label={`Mute ${t.label}`}
            >
              M
            </button>
            <button
              type="button"
              aria-pressed={t.solo}
              onClick={() => engine.setTrack(t.id, { solo: !t.solo })}
              className={`w-7 rounded border text-xs font-semibold ${t.solo ? "border-brand bg-brand/20 text-brand" : "border-line text-ink-muted"}`}
              aria-label={`Solo ${t.label}`}
            >
              S
            </button>
            <input
              type="range"
              min={0}
              max={1.5}
              step={0.01}
              value={t.volume}
              aria-label={`Volume ${t.label}`}
              onChange={(e) => engine.setTrack(t.id, { volume: Number(e.target.value) })}
              className="accent-[var(--brand)]"
            />
            <div className="flex items-center gap-1.5" aria-hidden="true">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised">
                <div
                  className={`h-full ${t.peak > 0.9 ? "bg-bad" : t.peak > 0.6 ? "bg-warn" : "bg-ok"}`}
                  style={{ width: `${Math.min(t.peak, 1) * 100}%` }}
                />
              </div>
              <span className={`size-2 rounded-full ${t.clipping ? "bg-bad" : "bg-raised"}`} title={t.clipping ? "Clipping" : undefined} />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-ink-muted">
        Scorciatoie: Spazio play/pausa · ←/→ ±5 s (Maiusc: una battuta) · 1-6 seleziona · M mute · S solo · L loop
      </p>
    </section>
  );
}
