import { useEffect, useState } from "react";

import { STEM_LABEL } from "@/components/StemsPanel";
import { Button, Notice, ProgressBar } from "@/components/ui";
import type { Player } from "@/hooks/usePlayer";
import {
  api,
  apiGet,
  asApiError,
  isJobActive,
  type ApiError,
  type ChordEvent,
  type Job,
  type StemInfo,
} from "@/lib/api";
import { getDownload, postDownload } from "@/lib/download";

interface ExportPanelProps {
  songId: string;
  songTitle: string;
  chords: ChordEvent[];
  chordLabel: (c: ChordEvent) => string;
  keyLabel: string | null;
  capo: number;
  notes: string[];
  player: Player | null;
  stems: StemInfo[] | null;
}

/** Export: accordi e testo (PDF, TXT, ChordPro), mix audio come nel player, stem. */
export function ExportPanel(props: ExportPanelProps) {
  const { songId, songTitle, chords, chordLabel, keyLabel, capo, notes, player, stems } = props;
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [audioFormat, setAudioFormat] = useState<"mp3" | "wav">("mp3");
  const [asPlayer, setAsPlayer] = useState(true);
  const [job, setJob] = useState<Job | null>(null);

  const sheet = async (format: "pdf" | "txt" | "chordpro"): Promise<void> => {
    setError(null);
    setBusy(format);
    try {
      const labels = Object.fromEntries(chords.map((c) => [c.id, chordLabel(c)]));
      const ext = format === "chordpro" ? "cho" : format;
      await postDownload(
        `/songs/${songId}/export`,
        { format, labels, key_label: keyLabel, capo, notes },
        `${songTitle}.${ext}`,
      );
    } catch (e) {
      setError(asApiError(e));
    } finally {
      setBusy(null);
    }
  };

  const exportAudio = async (): Promise<void> => {
    setError(null);
    const snap = player?.snap;
    const body =
      asPlayer && snap
        ? {
            format: audioFormat,
            rate: snap.rate,
            semitones: snap.semitones,
            tracks: snap.tracks.map((t) => ({
              id: t.id,
              volume: t.volume,
              muted: t.muted,
              solo: t.solo,
            })),
            key_label: keyLabel,
            capo,
          }
        : { format: audioFormat, key_label: keyLabel, capo };
    try {
      setJob(await api<Job>("POST", `/songs/${songId}/export`, body));
    } catch (e) {
      setError(asApiError(e));
    }
  };

  useEffect(() => {
    if (!job || !isJobActive(job)) return;
    const timer = window.setTimeout(() => {
      void apiGet<Job>(`/jobs/${job.id}`)
        .then((j) => {
          setJob(j);
          if (j.status === "ready") getDownload(`/exports/${j.id}`);
        })
        .catch((e: unknown) => setError(asApiError(e)));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [job]);

  const readyStems = (stems ?? []).filter((s) => s.status === "ready");
  const snap = player?.snap;
  const changed =
    snap &&
    (snap.rate !== 1 ||
      snap.semitones !== 0 ||
      snap.tracks.some((t) => t.muted || t.solo || t.volume !== 1));

  return (
    <section
      aria-labelledby="export-title"
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-3 text-xs"
    >
      <h2 id="export-title" className="text-sm font-semibold">
        Esporta
      </h2>
      {error && <Notice tone="error">{error.message}</Notice>}

      <div className="flex flex-col gap-1.5">
        <span className="text-ink-muted">
          Accordi e testo (come mostrati: trasposizione, capo, notazione)
        </span>
        <div className="flex flex-wrap gap-1.5">
          {(["pdf", "txt", "chordpro"] as const).map((f) => (
            <Button
              key={f}
              variant="secondary"
              disabled={busy !== null}
              onClick={() => void sheet(f)}
            >
              {busy === f ? "…" : f === "chordpro" ? "ChordPro" : f.toUpperCase()}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-ink-muted">Mix audio</span>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={audioFormat}
            onChange={(e) => setAudioFormat(e.target.value as "mp3" | "wav")}
            aria-label="Formato audio"
            className="rounded border border-line bg-ground px-1.5 py-1"
          >
            <option value="mp3">MP3 320k</option>
            <option value="wav">WAV 16 bit</option>
          </select>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={asPlayer}
              onChange={(e) => setAsPlayer(e.target.checked)}
              className="accent-[var(--brand)]"
            />
            come nel player
          </label>
          <Button
            variant="secondary"
            disabled={isJobActive(job)}
            onClick={() => void exportAudio()}
          >
            Esporta
          </Button>
        </div>
        {asPlayer && changed && (
          <p className="text-ink-muted">
            Include velocità {snap.rate.toFixed(2)}×, tonalità {snap.semitones > 0 ? "+" : ""}
            {snap.semitones} e il mixer attuale.
          </p>
        )}
        {job && isJobActive(job) && (
          <div aria-live="polite" className="flex flex-col gap-1">
            <span className="text-ink-muted">{job.message ?? "Export in corso…"}</span>
            <ProgressBar
              value={job.status === "queued" ? null : job.progress}
              label="Avanzamento dell'export"
            />
          </div>
        )}
        {job?.status === "ready" && (
          <button
            type="button"
            className="self-start text-brand underline"
            onClick={() => getDownload(`/exports/${job.id}`)}
          >
            Scarica di nuovo il file
          </button>
        )}
        {job?.status === "failed" && job.error && <Notice tone="error">{job.error.message}</Notice>}
      </div>

      {readyStems.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-ink-muted">Stem (FLAC)</span>
          <div className="flex flex-wrap gap-1.5">
            {readyStems.map((s) => (
              <Button
                key={s.type}
                variant="ghost"
                className="px-2"
                onClick={() => getDownload(`/songs/${songId}/stems/${s.type}/download`)}
              >
                {STEM_LABEL[s.type]}
              </Button>
            ))}
            <Button variant="secondary" onClick={() => getDownload(`/songs/${songId}/stems.zip`)}>
              Tutti (ZIP)
            </Button>
          </div>
        </div>
      )}
      <p className="text-ink-muted">I file vanno nella cartella Download di Windows.</p>
    </section>
  );
}
