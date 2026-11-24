import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/plugins/regions";

import type { SectionInfo, WaveformPeaks } from "@/lib/api";

interface WaveformProps {
  media: HTMLMediaElement;
  peaks: WaveformPeaks;
  sections: SectionInfo[];
}

/** Waveform da picchi precalcolati, collegata all'elemento audio, con le sezioni colorate. */
export function Waveform({ media, peaks, sections }: WaveformProps) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const styles = getComputedStyle(document.documentElement);
    const ws = WaveSurfer.create({
      container: container.current,
      media,
      peaks: [peaks.peaks],
      duration: peaks.duration_s,
      height: 96,
      barWidth: 2,
      barGap: 1,
      barRadius: 1,
      cursorWidth: 2,
      cursorColor: styles.getPropertyValue("--color-accent").trim() || "#f0a73a",
      waveColor: "#5b554e",
      progressColor: "#b9b1a6",
      normalize: true,
      dragToSeek: true,
    });
    const regions = ws.registerPlugin(RegionsPlugin.create());
    ws.on("ready", () => {
      for (const s of sections) {
        const label = document.createElement("span");
        label.textContent = s.name;
        label.className = "wave-region-label";
        regions.addRegion({
          start: s.start_s,
          end: s.end_s,
          color: `${s.color}26`,
          content: label,
          drag: false,
          resize: false,
        });
      }
    });
    return () => ws.destroy();
  }, [media, peaks, sections]);

  return (
    <div
      ref={container}
      role="img"
      aria-label={`Waveform del brano con ${sections.length} sezioni; clic per spostarsi`}
      className="rounded-md bg-ground px-1 py-2"
    />
  );
}
