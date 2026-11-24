import { useCallback, useEffect, useMemo, useState } from "react";

import type { BeatGrid, LoopState, TrackSpec } from "@/audio/engine";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { ChordDiagrams } from "@/components/ChordDiagrams";
import { ExportPanel } from "@/components/ExportPanel";
import { LyricsPanel } from "@/components/LyricsPanel";
import { MixerPanel } from "@/components/MixerPanel";
import { PracticeControls, type PracticeView } from "@/components/PracticeControls";
import { StemsPanel, STEM_LABEL } from "@/components/StemsPanel";
import { TabsPanel } from "@/components/TabsPanel";
import { SectionsNav } from "@/components/SectionsNav";
import { TransportBar } from "@/components/TransportBar";
import { Notice } from "@/components/ui";
import { useAnalysis } from "@/hooks/useAnalysis";
import { usePlayer, usePlayerTime } from "@/hooks/usePlayer";
import { usePlayerShortcuts } from "@/hooks/usePlayerShortcuts";
import { useStems } from "@/hooks/useStems";
import { api, apiGet, asApiError, type ApiError, type ChordEvent, type Song } from "@/lib/api";
import { displayChord, keyName, parseKey, transposeKey, type DisplayedChord } from "@/lib/music";

interface SongWorkspaceProps {
  song: Song;
  busy: boolean;
  onChanged: () => void;
  onReanalyze: () => void;
}

interface DisplayPrefs {
  notation: PracticeView["notation"];
  instrument: PracticeView["instrument"];
  compact: boolean;
}

/** Brano pronto: player, waveform, mixer, trasposizione, accordi, diagrammi, testi, tab. */
export function SongWorkspace({ song, busy, onChanged, onReanalyze }: SongWorkspaceProps) {
  const [rev, setRev] = useState(0);
  const analysisState = useAnalysis(song.id, `${song.updated_at}:${rev}`);
  const stems = useStems(song.id, song.updated_at);
  const analysis = analysisState.kind === "ready" ? analysisState.analysis : null;
  const [error, setError] = useState<ApiError | null>(null);

  // ------------------------------------------------------------ visualizzazione
  const [view, setView] = useState<PracticeView>({
    transpose: song.transpose,
    capo: song.capo,
    simplification: song.simplification,
    notation: "american",
    instrument: "guitar",
    compact: false,
  });
  useEffect(() => {
    void apiGet<DisplayPrefs>("/settings/display")
      .then((p) => setView((v) => ({ ...v, ...p })))
      .catch(() => undefined);
  }, []);

  const changeView = useCallback(
    (patch: Partial<PracticeView>) => {
      setView((v) => {
        const next = { ...v, ...patch };
        if ("transpose" in patch || "capo" in patch || "simplification" in patch) {
          void api("PATCH", `/songs/${song.id}/view`, {
            transpose: next.transpose,
            capo: next.capo,
            simplification: next.simplification,
          }).catch((e: unknown) => setError(asApiError(e)));
        }
        if ("notation" in patch || "instrument" in patch || "compact" in patch) {
          void api("PUT", "/settings/display", {
            notation: next.notation,
            instrument: next.instrument,
            compact: next.compact,
          }).catch((e: unknown) => setError(asApiError(e)));
        }
        return next;
      });
    },
    [song.id],
  );

  const settings = useMemo(
    () => ({
      transpose: view.transpose,
      capo: view.capo,
      simplification: view.simplification,
      notation: view.notation,
      key: analysis?.key ?? null,
    }),
    [view.transpose, view.capo, view.simplification, view.notation, analysis?.key],
  );
  const display = useCallback(
    (c: ChordEvent): DisplayedChord | null =>
      c.chord === "N" ? null : displayChord(c.chord, settings, c.simplify_exempt),
    [settings],
  );
  const chordLabel = useCallback((c: ChordEvent) => display(c)?.label ?? c.chord, [display]);

  /** Accordi sonanti (senza capo) con la durata complessiva, per suggerire il capo. */
  const sounding = useMemo(() => {
    if (!analysis) return [];
    const totals = new Map<string, number>();
    for (const c of analysis.chords) {
      if (c.chord === "N") continue;
      const d = displayChord(
        c.chord,
        { ...settings, capo: 0, notation: "american" },
        c.simplify_exempt,
      );
      if (d) totals.set(d.shape, (totals.get(d.shape) ?? 0) + (c.end_s - c.start_s));
    }
    return [...totals].map(([symbol, duration]) => ({ symbol, duration }));
  }, [analysis, settings]);

  const shapes = useMemo(() => {
    if (!analysis) return [];
    const seen = new Map<string, string>();
    for (const c of analysis.chords) {
      const d = display(c);
      if (d && !seen.has(d.shape)) seen.set(d.shape, d.label);
    }
    return [...seen].map(([shape, label]) => ({ shape, label }));
  }, [analysis, display]);

  const onExempt = useCallback(
    (c: ChordEvent, exempt: boolean) => {
      void api("PATCH", `/songs/${song.id}/chords/${c.id}`, { simplify_exempt: exempt })
        .then(() => setRev((r) => r + 1))
        .catch((e: unknown) => setError(asApiError(e)));
    },
    [song.id],
  );

  const originalKey = parseKey(analysis?.key ?? null);
  const exportKey = originalKey ? keyName(transposeKey(originalKey, view.transpose)) : null;
  const exportNotes = useMemo(() => {
    const out: string[] = [];
    if (view.transpose !== 0)
      out.push(
        `Trasposto di ${view.transpose > 0 ? "+" : ""}${view.transpose} semitoni (originale ${analysis?.key ?? "?"})`,
      );
    if (view.capo > 0) out.push(`Accordi come forme con capo al ${view.capo}° tasto`);
    if (view.simplification !== "original")
      out.push(`Semplificazione: ${view.simplification === "easy" ? "facile" : "intermedia"}`);
    if (view.notation !== "american")
      out.push(`Notazione ${view.notation === "italian" ? "italiana" : "numerica"}`);
    return out;
  }, [view.transpose, view.capo, view.simplification, view.notation, analysis?.key]);

  // ------------------------------------------------------------------- player
  const tracks = useMemo<TrackSpec[]>(() => {
    if (stems === null) return [];
    const ready = stems.filter((s) => s.status === "ready");
    if (ready.length === 6)
      return ready.map((s) => ({ id: s.type, label: STEM_LABEL[s.type], url: s.url }));
    return song.audio_url ? [{ id: "mix", label: "Mix completo", url: song.audio_url }] : [];
  }, [stems, song.audio_url]);

  const grid = useMemo<BeatGrid | null>(
    () =>
      analysis
        ? {
            beats: analysis.beats.map((b) => b.time_s),
            downbeats: analysis.beats.map((b) => b.is_downbeat),
            bpm: analysis.bpm,
            beatsPerBar: analysis.beats_per_bar,
          }
        : null,
    [analysis],
  );
  const downbeats = useMemo(
    () => (analysis ? analysis.beats.filter((b) => b.is_downbeat).map((b) => b.time_s) : []),
    [analysis],
  );

  const player = usePlayer(tracks, grid);
  const time = usePlayerTime(player);
  const [selected, setSelected] = useState<string | null>(null);
  const [snap, setSnap] = useState(true);
  usePlayerShortcuts({ player, selected, onSelect: setSelected, downbeats });

  const engine = player?.engine ?? null;
  const seek = useCallback((t: number) => engine?.seek(t), [engine]);
  const setLoop = useCallback((loop: LoopState) => engine?.setLoop(loop), [engine]);
  const hasStems = tracks.length === 6;
  const duration = player?.snap.duration || song.duration_s || 0;
  const activeChord = analysis?.chords.find((c) => time >= c.start_s && time < c.end_s);
  const activeShape = activeChord ? (display(activeChord)?.shape ?? null) : null;

  return (
    <>
      {error && <Notice tone="error">{error.message}</Notice>}
      {analysis && (
        <SectionsNav
          sections={analysis.sections}
          time={time}
          onSeek={seek}
          onLoop={(a, b) => setLoop({ a, b, enabled: true })}
        />
      )}
      <div className="grid grid-cols-[minmax(0,1fr)_22rem] items-start gap-5">
        <div className="flex min-w-0 flex-col gap-5">
          <AnalysisPanel
            state={analysisState}
            duration={duration}
            time={time}
            loop={player?.snap.loop ?? null}
            snap={snap}
            onSeek={seek}
            onLoop={setLoop}
            busy={busy}
            onReanalyze={onReanalyze}
            display={display}
            compact={view.compact}
            onExempt={onExempt}
          >
            <LyricsPanel song={song} time={time} onSeek={seek} chordLabel={chordLabel} />
            <TabsPanel
              song={song}
              downbeats={downbeats}
              duration={duration}
              transpose={view.transpose}
              capo={view.capo}
              time={time}
              onSeek={seek}
            />
            <StemsPanel song={song} stems={stems} onChanged={onChanged} />
          </AnalysisPanel>
        </div>

        <aside
          aria-label="Mixer, tonalità e diagrammi"
          className="sticky top-0 flex max-h-[calc(100vh-9rem)] flex-col gap-4 overflow-y-auto pb-4"
        >
          {player ? (
            <MixerPanel
              player={player}
              selected={selected}
              onSelect={setSelected}
              hasStems={hasStems}
            />
          ) : (
            <div className="h-48 animate-pulse rounded-lg bg-surface" aria-hidden="true" />
          )}
          {analysis?.analyzed && (
            <PracticeControls
              view={view}
              onChange={changeView}
              originalKey={analysis.key}
              sounding={sounding}
              audioSemitones={player?.snap.pitchAvailable ? player.snap.semitones : null}
              onApplyToAudio={
                player?.snap.pitchAvailable ? () => engine?.setSemitones(view.transpose) : null
              }
            />
          )}
          {shapes.length > 0 && (
            <section
              aria-labelledby="diagrams-title"
              className="rounded-lg border border-line bg-surface p-3"
            >
              <h2 id="diagrams-title" className="mb-2 text-sm font-semibold">
                Diagrammi
              </h2>
              <ChordDiagrams
                shapes={shapes}
                instrument={view.instrument}
                activeShape={activeShape}
              />
            </section>
          )}
          {analysis?.analyzed && (
            <ExportPanel
              songId={song.id}
              songTitle={song.title}
              chords={analysis.chords}
              chordLabel={chordLabel}
              keyLabel={exportKey}
              capo={view.capo}
              notes={exportNotes}
              player={player}
              stems={stems}
            />
          )}
        </aside>
      </div>

      {player && (
        <TransportBar
          player={player}
          time={time}
          beats={grid?.beats ?? []}
          snap={snap}
          onSnapChange={setSnap}
          hasBpm={Boolean(grid?.bpm && grid.beats.length > 0)}
        />
      )}
    </>
  );
}
