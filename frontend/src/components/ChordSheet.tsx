import { Fragment, useMemo, useState } from "react";

import type { DisplayedChord } from "@/lib/music";

import type { Analysis, ChordEvent, SectionInfo } from "@/lib/api";

interface Bar {
  index: number;
  start: number;
  end: number;
  chords: ChordEvent[];
  /** Accordo che prosegue dalla battuta precedente (nessun cambio in questa battuta). */
  carried: ChordEvent | null;
  section: SectionInfo | null;
}

function buildBars(analysis: Analysis): Bar[] {
  const { beats, chords, sections } = analysis;
  const starts = beats.filter((b) => b.is_downbeat).map((b) => b.time_s);
  const first = beats[0];
  if (first && starts.length > 0 && first.time_s < (starts[0] ?? 0) - 0.05) {
    starts.unshift(first.time_s); // anacrusi
  }
  const songEnd = Math.max(chords.at(-1)?.end_s ?? 0, beats.at(-1)?.time_s ?? 0);
  const bars: Bar[] = [];
  let sectionIdx = -1;
  starts.forEach((start, i) => {
    const end = starts[i + 1] ?? songEnd;
    const inBar = chords.filter((c) => c.start_s >= start - 0.05 && c.start_s < end - 0.05);
    const carried =
      inBar.length === 0 || (inBar[0]?.start_s ?? 0) > start + 0.05
        ? (chords.find((c) => c.start_s <= start + 0.05 && c.end_s > start + 0.05) ?? null)
        : null;
    let section: SectionInfo | null = null;
    while (sectionIdx + 1 < sections.length && (sections[sectionIdx + 1]?.start_s ?? Infinity) < end - 0.05) {
      sectionIdx += 1;
      section = sections[sectionIdx] ?? null;
    }
    bars.push({ index: i, start, end, chords: inBar, carried, section });
  });
  return bars;
}

interface ChordSheetProps {
  analysis: Analysis;
  time: number;
  onSeek: (time: number) => void;
  /** Ripete un intervallo (battuta con Maiusc+clic, oppure sezione). */
  onLoop: (start: number, end: number) => void;
  /** Accordo come va mostrato (semplificazione, trasposizione, capo, notazione). */
  display: (c: ChordEvent) => DisplayedChord | null;
  compact: boolean;
  /** Esclude (o reinclude) un accordo dalla semplificazione. */
  onExempt: (c: ChordEvent, exempt: boolean) => void;
}

/** Accordi per battuta, con le sezioni e l'evidenziazione della posizione corrente. */
export function ChordSheet(props: ChordSheetProps) {
  const { analysis, time, onSeek, onLoop, display, compact, onExempt } = props;
  const bars = useMemo(() => buildBars(analysis), [analysis]);
  const visible = (c: ChordEvent): boolean => c.chord !== "N";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = analysis.chords.find((c) => c.id === selectedId) ?? null;
  const selectedView = selected ? display(selected) : null;
  const chip = (c: ChordEvent, onLoopBar?: () => void) => (
    <ChordChip
      key={c.id}
      chord={c}
      view={display(c)}
      compact={compact}
      active={time >= c.start_s && time < c.end_s}
      onSeek={(t) => {
        setSelectedId(c.id);
        onSeek(t);
      }}
      {...(onLoopBar ? { onLoopBar } : {})}
    />
  );
  const detail = selected && selectedView && (selectedView.simplifiedReason || selected.simplify_exempt || selectedView.original) && (
    <p className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-ground px-3 py-2 text-xs text-ink-muted" aria-live="polite">
      <span className="font-mono font-semibold text-ink">{selectedView.label}</span>
      {selectedView.original && <span>originale: <span className="font-mono">{selectedView.original}</span></span>}
      {selectedView.simplifiedReason && <span>· {selectedView.simplifiedReason}</span>}
      {selectedView.simplifiedReason && (
        <button type="button" className="rounded px-1.5 py-0.5 text-accent hover:bg-raised" onClick={() => onExempt(selected, true)}>
          Ripristina questo accordo
        </button>
      )}
      {selected.simplify_exempt && (
        <button type="button" className="rounded px-1.5 py-0.5 text-accent hover:bg-raised" onClick={() => onExempt(selected, false)}>
          Semplifica di nuovo
        </button>
      )}
    </p>
  );

  if (bars.length === 0) {
    return (
      <ul className="flex flex-wrap gap-2" aria-label="Accordi">
        {analysis.chords.filter(visible).map((c) => (
          <li key={c.id}>{chip(c)}</li>
        ))}
        {detail}
      </ul>
    );
  }

  return (
    <div>
    <div className="flex flex-wrap gap-y-2" aria-label="Accordi per battuta" role="list">
      {bars.map((bar) => {
        const activeBar = time >= bar.start && time < bar.end;
        return (
          <Fragment key={bar.index}>
            {bar.section && (
              <div className="mt-3 flex basis-full items-center gap-2 first:mt-0" role="presentation">
                <span className="size-2.5 rounded-sm" style={{ background: bar.section.color }} />
                <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {bar.section.name}
                </span>
                <button
                  type="button"
                  className="rounded px-1.5 text-xs text-ink-muted hover:bg-raised hover:text-ink"
                  onClick={() => bar.section && onLoop(bar.section.start_s, bar.section.end_s)}
                  title="Ripeti questa sezione"
                >
                  ↻ ripeti
                </button>
              </div>
            )}
            <div
              role="listitem"
              className={`flex min-w-0 items-center gap-1 border-l px-2 ${compact ? "h-9 w-1/8" : "h-14 w-1/4"} ${
                activeBar ? "border-accent bg-accent/10" : "border-line"
              }`}
            >
              {bar.carried && visible(bar.carried) && (
                <button
                  type="button"
                  onClick={(e) => (e.shiftKey ? onLoop(bar.start, bar.end) : onSeek(bar.start))}
                  className="truncate font-mono text-sm text-ink-muted/60 hover:text-ink-muted"
                  title="Prosegue dalla battuta precedente"
                >
                  {display(bar.carried)?.label ?? bar.carried.chord}
                </button>
              )}
              {bar.chords.filter(visible).map((c) => chip(c, () => onLoop(bar.start, bar.end)))}
            </div>
          </Fragment>
        );
      })}
    </div>
    {detail}
    </div>
  );
}

function ChordChip({
  chord,
  view,
  compact,
  active,
  onSeek,
  onLoopBar,
}: {
  chord: ChordEvent;
  view: DisplayedChord | null;
  compact: boolean;
  active: boolean;
  onSeek: (t: number) => void;
  onLoopBar?: () => void;
}) {
  const lowConfidence = chord.confidence !== null && chord.confidence < 0.4;
  const label = view?.label ?? chord.chord;
  const simplified = Boolean(view?.simplifiedReason);
  return (
    <button
      type="button"
      onClick={(e) => (e.shiftKey && onLoopBar ? onLoopBar() : onSeek(chord.start_s))}
      aria-current={active ? "true" : undefined}
      title={[
        label,
        view?.original ? `originale ${view.original}` : null,
        view?.simplifiedReason ? `semplificato: ${view.simplifiedReason}` : null,
        lowConfidence ? `rilevamento incerto (${Math.round((chord.confidence ?? 0) * 100)}%)` : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      className={`flex flex-col items-start truncate rounded px-1.5 py-0.5 font-mono text-sm font-semibold leading-tight transition-colors ${simplified ? "outline-dashed outline-1 outline-accent/60" : ""} ${
        active
          ? "bg-accent text-ground"
          : lowConfidence
            ? "text-ink underline decoration-warn/70 decoration-dotted underline-offset-4 hover:bg-raised"
            : "text-ink hover:bg-raised"
      }`}
    >
      <span>{label}</span>
      {!compact && view?.original && (
        <span className={`text-[10px] font-normal ${active ? "text-ground/80" : "text-ink-muted"}`}>{view.original}</span>
      )}
    </button>
  );
}
