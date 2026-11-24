import { useState } from "react";

import { ChordSheet } from "@/components/ChordSheet";
import { Button, Notice } from "@/components/ui";
import { Waveform } from "@/components/Waveform";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useMediaTime } from "@/hooks/useMediaTime";
import type { Song } from "@/lib/api";

function confidenceLabel(value: number | null): { text: string; tone: string } {
  if (value === null) return { text: "—", tone: "text-ink-muted" };
  if (value >= 0.66) return { text: "affidabilità alta", tone: "text-ok" };
  if (value >= 0.33) return { text: "affidabilità media", tone: "text-warn" };
  return { text: "affidabilità bassa", tone: "text-bad" };
}

interface AnalysisPanelProps {
  song: Song;
  onReanalyze: () => void;
  busy: boolean;
}

export function AnalysisPanel({ song, onReanalyze, busy }: AnalysisPanelProps) {
  const state = useAnalysis(song.id, song.updated_at);
  const [media, setMedia] = useState<HTMLAudioElement | null>(null);
  const time = useMediaTime(media);
  const [confirmReanalyze, setConfirmReanalyze] = useState(false);

  const seek = (t: number): void => {
    if (!media) return;
    media.currentTime = t;
    if (media.paused) void media.play().catch(() => undefined);
  };

  return (
    <div className="flex flex-col gap-5">
      {state.kind === "ready" && state.analysis.analyzed && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Fact
            label="Tonalità"
            value={state.analysis.key ?? "—"}
            confidence={state.analysis.key_confidence}
          />
          <Fact
            label="BPM"
            value={state.analysis.bpm ? state.analysis.bpm.toFixed(0) : "—"}
            confidence={state.analysis.bpm_confidence}
          />
          <Fact
            label="Battute"
            value={String(state.analysis.beats.filter((b) => b.is_downbeat).length)}
            confidence={null}
            note={`${state.analysis.beats_per_bar}/4 (presunto)`}
          />
        </div>
      )}

      <section aria-label="Ascolto" className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
        {state.kind === "ready" && state.waveform && media && (
          <Waveform media={media} peaks={state.waveform} sections={state.analysis.sections} />
        )}
        {song.audio_url && (
          <audio ref={setMedia} controls preload="metadata" src={song.audio_url} className="w-full">
            Il tuo sistema non riesce a riprodurre questo audio.
          </audio>
        )}
      </section>

      {state.kind === "loading" && (
        <div aria-hidden="true" className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-md bg-surface" />
          ))}
        </div>
      )}
      {state.kind === "error" && <Notice tone="error">{state.error.message}</Notice>}

      {state.kind === "ready" && state.analysis.analyzed && (
        <section aria-labelledby="chords-title" className="rounded-lg border border-line bg-surface p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="chords-title" className="text-base font-semibold">
              Accordi
            </h2>
            <p className="text-xs text-ink-muted">
              Rilevati automaticamente: possono contenere errori. Sottolineati = incerti. Clic su
              un accordo per ascoltarlo.
            </p>
          </div>
          {state.analysis.chords.length > 0 ? (
            <ChordSheet analysis={state.analysis} time={time} onSeek={seek} />
          ) : (
            <p className="text-sm text-ink-muted">Nessun accordo rilevato.</p>
          )}
        </section>
      )}

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
