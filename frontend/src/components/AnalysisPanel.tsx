import { useState, type ReactNode } from "react";

import type { LoopState } from "@/audio/engine";
import { ChordSheet } from "@/components/ChordSheet";
import { Button, Notice } from "@/components/ui";
import { WaveformCanvas } from "@/components/WaveformCanvas";
import type { AnalysisState } from "@/hooks/useAnalysis";
import type { ChordEvent } from "@/lib/api";
import type { DisplayedChord } from "@/lib/music";

function confidenceLabel(value: number | null): { text: string; tone: string } {
  if (value === null) return { text: "—", tone: "text-ink-muted" };
  if (value >= 0.66) return { text: "affidabilità alta", tone: "text-ok" };
  if (value >= 0.33) return { text: "affidabilità media", tone: "text-warn" };
  return { text: "affidabilità bassa", tone: "text-bad" };
}

interface AnalysisPanelProps {
  state: AnalysisState;
  duration: number;
  time: number;
  loop: LoopState | null;
  snap: boolean;
  onSeek: (t: number) => void;
  onLoop: (loop: LoopState) => void;
  onReanalyze: () => void;
  busy: boolean;
  /** Contenuto tra waveform e accordi (es. il mixer). */
  afterWaveform?: ReactNode;
  /** Controlli di trasposizione e visualizzazione, sopra gli accordi. */
  practice?: ReactNode;
  /** Diagrammi, in fondo alla sezione degli accordi. */
  diagrams?: ReactNode;
  display: (c: ChordEvent) => DisplayedChord | null;
  compact: boolean;
  onExempt: (c: ChordEvent, exempt: boolean) => void;
  /** Contenuto sotto gli accordi (es. i testi). */
  children?: ReactNode;
}

export function AnalysisPanel(props: AnalysisPanelProps) {
  const { state, duration, time, loop, snap, onSeek, onLoop, onReanalyze, busy, afterWaveform, practice, diagrams, display, compact, onExempt, children } = props;
  const [confirmReanalyze, setConfirmReanalyze] = useState(false);
  const analysis = state.kind === "ready" ? state.analysis : null;

  return (
    <div className="flex flex-col gap-5">
      {analysis?.analyzed && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Fact label="Tonalità" value={analysis.key ?? "—"} confidence={analysis.key_confidence} />
          <Fact label="BPM" value={analysis.bpm ? analysis.bpm.toFixed(0) : "—"} confidence={analysis.bpm_confidence} />
          <Fact
            label="Battute"
            value={String(analysis.beats.filter((b) => b.is_downbeat).length)}
            confidence={null}
            note={`${analysis.beats_per_bar}/4 (presunto)`}
          />
        </div>
      )}

      {state.kind === "ready" && state.waveform && duration > 0 && (
        <section aria-label="Waveform" className="rounded-lg border border-line bg-surface p-3">
          <WaveformCanvas
            peaks={state.waveform}
            duration={duration}
            sections={state.analysis.sections}
            beats={state.analysis.beats.map((b) => b.time_s)}
            time={time}
            loop={loop}
            snap={snap}
            onSeek={onSeek}
            onLoop={onLoop}
          />
        </section>
      )}

      {afterWaveform}

      {state.kind === "loading" && (
        <div aria-hidden="true" className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-md bg-surface" />
          ))}
        </div>
      )}
      {state.kind === "error" && <Notice tone="error">{state.error.message}</Notice>}

      {analysis?.analyzed && practice}

      {analysis?.analyzed && (
        <section aria-labelledby="chords-title" className="rounded-lg border border-line bg-surface p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="chords-title" className="text-base font-semibold">
              Accordi
            </h2>
            <p className="text-xs text-ink-muted">
              Rilevati automaticamente: possono contenere errori. Sottolineati = incerti. Clic: ascolta da
              lì · Maiusc+clic: ripeti la battuta.
            </p>
          </div>
          {analysis.chords.length > 0 ? (
            <ChordSheet
              analysis={analysis}
              time={time}
              onSeek={onSeek}
              onLoop={(a, b) => onLoop({ a, b, enabled: true })}
              display={display}
              compact={compact}
              onExempt={onExempt}
            />
          ) : (
            <p className="text-sm text-ink-muted">Nessun accordo rilevato.</p>
          )}
          {diagrams && <div className="mt-4 border-t border-line pt-3">{diagrams}</div>}
        </section>
      )}

      {children}

      {state.kind === "ready" && (
        <div className="flex justify-end">
          {confirmReanalyze ? (
            <Notice
              tone="warn"
              title="Rianalizzare il brano?"
              action={
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={() => setConfirmReanalyze(false)}>
                    Annulla
                  </Button>
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={() => {
                      setConfirmReanalyze(false);
                      onReanalyze();
                    }}
                  >
                    Rianalizza
                  </Button>
                </div>
              }
            >
              I risultati attuali, comprese eventuali modifiche, verranno sostituiti.
            </Notice>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmReanalyze(true)}>
              Rianalizza
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function Fact({
  label,
  value,
  confidence,
  note,
}: {
  label: string;
  value: string;
  confidence: number | null;
  note?: string;
}) {
  const conf = confidenceLabel(confidence);
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-0.5 font-mono text-xl font-semibold">{value}</p>
      <p className={`text-xs ${note ? "text-ink-muted" : conf.tone}`}>{note ?? conf.text}</p>
    </div>
  );
}
