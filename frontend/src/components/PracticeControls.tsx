import { useEffect, useState } from "react";

import type { DiagramInstrument } from "@/components/ChordDiagrams";
import { Button } from "@/components/ui";
import { keyName, parseKey, transposeKey, type Notation, type SimplifyLevel } from "@/lib/music";
import { loadDb, suggestCapo, type CapoSuggestion } from "@/lib/shapes";

export interface PracticeView {
  transpose: number;
  capo: number;
  simplification: SimplifyLevel;
  notation: Notation;
  instrument: DiagramInstrument;
  compact: boolean;
}

interface PracticeControlsProps {
  view: PracticeView;
  onChange: (patch: Partial<PracticeView>) => void;
  originalKey: string | null;
  /** Accordi sonanti (dopo semplificazione e trasposizione) con durata, per il capo. */
  sounding: { symbol: string; duration: number }[];
  audioSemitones: number | null;
  onApplyToAudio: (() => void) | null;
}

export function PracticeControls(props: PracticeControlsProps) {
  const { view, onChange, originalKey, sounding, audioSemitones, onApplyToAudio } = props;
  const [suggestions, setSuggestions] = useState<CapoSuggestion[] | null>(null);
  const key = parseKey(originalKey);
  const newKey = key ? keyName(transposeKey(key, view.transpose)) : null;

  useEffect(() => {
    let alive = true;
    setSuggestions(null);
    if (sounding.length === 0) return;
    void loadDb("guitar").then((db) => alive && setSuggestions(suggestCapo(db, sounding)));
    return () => {
      alive = false;
    };
  }, [sounding]);

  const best = suggestions?.[0];
  const current = suggestions?.find((s) => s.capo === view.capo);

  return (
    <section aria-label="Trasposizione e visualizzazione" className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-3 text-xs [&>label]:justify-between">
      <div className="flex items-center gap-1">
        <span className="text-ink-muted">Trasponi</span>
        <Button variant="ghost" className="px-2 py-0.5" disabled={view.transpose <= -11} onClick={() => onChange({ transpose: view.transpose - 1 })} aria-label="Un semitono sotto">
          −
        </Button>
        <span className="w-7 text-center font-mono">{view.transpose > 0 ? `+${view.transpose}` : view.transpose}</span>
        <Button variant="ghost" className="px-2 py-0.5" disabled={view.transpose >= 11} onClick={() => onChange({ transpose: view.transpose + 1 })} aria-label="Un semitono sopra">
          +
        </Button>
        {originalKey && (
          <span className="ml-1 font-mono">
            {view.transpose === 0 ? originalKey : `${originalKey} → ${newKey}`}
          </span>
        )}
        {view.transpose !== 0 && (
          <Button variant="ghost" className="px-1.5 py-0.5" onClick={() => onChange({ transpose: 0 })}>
            Originale
          </Button>
        )}
        {onApplyToAudio && audioSemitones !== view.transpose && (
          <Button variant="ghost" className="px-1.5 py-0.5" onClick={onApplyToAudio} title="Cambia la tonalità dell'audio dello stesso intervallo">
            Applica all'audio
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1">
          <span className="text-ink-muted">Capo</span>
          <select value={view.capo} onChange={(e) => onChange({ capo: Number(e.target.value) })} className="rounded border border-line bg-ground px-1 py-0.5">
            {Array.from({ length: 8 }, (_, i) => (
              <option key={i} value={i}>
                {i === 0 ? "nessuno" : i}
              </option>
            ))}
          </select>
        </label>
        {best && best.capo !== view.capo && (
          <Button
            variant="ghost"
            className="px-1.5 py-0.5"
            onClick={() => onChange({ capo: best.capo })}
            title={`Barré: ${Math.round(best.barres)} s invece di ${Math.round(current?.barres ?? 0)} s`}
          >
            Suggerito: {best.capo === 0 ? "senza capo" : `capo ${best.capo}`}
          </Button>
        )}
      </div>

      <label className="flex items-center gap-1">
        <span className="text-ink-muted">Semplificazione</span>
        <select value={view.simplification} onChange={(e) => onChange({ simplification: e.target.value as SimplifyLevel })} className="rounded border border-line bg-ground px-1 py-0.5">
          <option value="original">originale</option>
          <option value="intermediate">intermedia</option>
          <option value="easy">facile</option>
        </select>
      </label>

      <label className="flex items-center gap-1">
        <span className="text-ink-muted">Notazione</span>
        <select value={view.notation} onChange={(e) => onChange({ notation: e.target.value as Notation })} className="rounded border border-line bg-ground px-1 py-0.5">
          <option value="american">americana (C, Am)</option>
          <option value="italian">italiana (Do, Lam)</option>
          <option value="numeric">numerica (1, 6m)</option>
        </select>
      </label>

      <label className="flex items-center gap-1">
        <span className="text-ink-muted">Strumento</span>
        <select value={view.instrument} onChange={(e) => onChange({ instrument: e.target.value as DiagramInstrument })} className="rounded border border-line bg-ground px-1 py-0.5">
          <option value="guitar">chitarra</option>
          <option value="ukulele">ukulele</option>
          <option value="piano">pianoforte</option>
        </select>
      </label>

      <label className="flex items-center gap-1">
        <input type="checkbox" checked={view.compact} onChange={(e) => onChange({ compact: e.target.checked })} className="accent-[var(--brand)]" />
        Vista compatta
      </label>
    </section>
  );
}
