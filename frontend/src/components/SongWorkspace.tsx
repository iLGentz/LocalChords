import { useCallback, useMemo, useState } from "react";

import type { BeatGrid, LoopState, TrackSpec } from "@/audio/engine";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { LyricsPanel } from "@/components/LyricsPanel";
import { MixerPanel } from "@/components/MixerPanel";
import { StemsPanel, STEM_LABEL } from "@/components/StemsPanel";
import { TransportBar } from "@/components/TransportBar";
import { Notice } from "@/components/ui";
import { useAnalysis } from "@/hooks/useAnalysis";
import { usePlayer, usePlayerTime } from "@/hooks/usePlayer";
import { usePlayerShortcuts } from "@/hooks/usePlayerShortcuts";
import { useStems } from "@/hooks/useStems";
import type { Song } from "@/lib/api";

interface SongWorkspaceProps {
  song: Song;
  busy: boolean;
  onChanged: () => void;
  onReanalyze: () => void;
}

/** Brano pronto: player (mix o 6 stem), waveform, mixer, accordi, testi, trasporto. */
export function SongWorkspace({ song, busy, onChanged, onReanalyze }: SongWorkspaceProps) {
  const analysisState = useAnalysis(song.id, song.updated_at);
  const stems = useStems(song.id, song.updated_at);
  const analysis = analysisState.kind === "ready" ? analysisState.analysis : null;

  const tracks = useMemo<TrackSpec[]>(() => {
    if (stems === null) return [];
    const ready = stems.filter((s) => s.status === "ready");
    if (ready.length === 6) return ready.map((s) => ({ id: s.type, label: STEM_LABEL[s.type], url: s.url }));
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

  return (
    <>
      <AnalysisPanel
        state={analysisState}
        duration={player?.snap.duration || song.duration_s || 0}
        time={time}
        loop={player?.snap.loop ?? null}
        snap={snap}
        onSeek={seek}
        onLoop={setLoop}
        busy={busy}
        onReanalyze={onReanalyze}
        afterWaveform={
          player ? (
            <MixerPanel player={player} selected={selected} onSelect={setSelected} hasStems={hasStems} />
          ) : null
        }
      >
        {player?.snap.status === "playing" && player.snap.semitones !== 0 && (
          <Notice tone="info">
            L'audio è trasposto di {player.snap.semitones > 0 ? "+" : ""}
            {player.snap.semitones} semitoni: la trasposizione degli accordi arriva nella prossima fase.
          </Notice>
        )}
        <LyricsPanel song={song} time={time} onSeek={seek} />
        <StemsPanel song={song} stems={stems} onChanged={onChanged} />
      </AnalysisPanel>

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
