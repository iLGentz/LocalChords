import { useEffect, useMemo, useState } from "react";

import { Button, Notice } from "@/components/ui";
import { api, apiGet, asApiError, type ApiError, type Song } from "@/lib/api";

interface TabNote {
  string: number;
  fret: number;
  pitch_midi: number;
  start_s: number;
  duration_s: number;
}

interface InstrumentTab {
  tuning: number[];
  notes: TabNote[];
}

interface TabsData {
  available_stems: string[];
  guitar: InstrumentTab | null;
  bass: InstrumentTab | null;
  job: { id: string; status: string; progress: number; message: string | null; error: { message: string } | null } | null;
}

type Kind = "guitar" | "bass";
const STRING_NAMES: Record<Kind, string[]> = { guitar: ["e", "B", "G", "D", "A", "E"], bass: ["G", "D", "A", "E"] };
const SLOTS = 16;
const BARS_PER_ROW = 4;
const MAX_FRET = 22;

interface TabsPanelProps {
  song: Song;
  downbeats: number[];
  duration: number;
  transpose: number;
  capo: number;
  time: number;
  onSeek: (t: number) => void;
}

/** Riposiziona la nota dopo trasposizione e capo; null se non è suonabile. */
function refret(n: TabNote, tuning: number[], transpose: number, capo: number): { string: number; fret: number } | null {
  const pitch = n.pitch_midi + transpose;
  const strings = tuning.length;
  const fretOn = (string: number): number => pitch - ((tuning[strings - string] ?? 0) + capo);
  const same = fretOn(n.string);
  if (same >= 0 && same <= MAX_FRET) return { string: n.string, fret: same };
  let best: { string: number; fret: number } | null = null;
  for (let s = 1; s <= strings; s++) {
    const f = fretOn(s);
    if (f >= 0 && f <= MAX_FRET && (best === null || Math.abs(s - n.string) < Math.abs(best.string - n.string))) best = { string: s, fret: f };
  }
  return best;
}

export function TabsPanel({ song, downbeats, duration, transpose, capo, time, onSeek }: TabsPanelProps) {
  const [data, setData] = useState<TabsData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [kind, setKind] = useState<Kind>("guitar");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    apiGet<TabsData>(`/songs/${song.id}/tabs`, controller.signal)
      .then((d) => {
        setData(d);
        if (!d.guitar && d.bass) setKind("bass");
        if (d.job && ["queued", "analyzing"].includes(d.job.status)) timer = window.setTimeout(() => setTick((t) => t + 1), 1500);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(asApiError(e));
      });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [song.id, song.updated_at, tick]);

  const tab = data ? data[kind] : null;
  const bars = useMemo(() => {
    const starts = downbeats.length > 1 ? downbeats : Array.from({ length: Math.ceil(duration / 2) }, (_, i) => i * 2);
    return starts.map((start, i) => ({ start, end: starts[i + 1] ?? duration }));
  }, [downbeats, duration]);

  const rows = useMemo(() => {
    if (!tab) return [];
    const names = STRING_NAMES[kind];
    const shiftCapo = kind === "guitar" ? capo : 0;
    const grid = bars.map(() => names.map(() => new Array<string>(SLOTS).fill("")));
    let barIdx = 0;
    for (const n of tab.notes) {
      while (barIdx < bars.length - 1 && n.start_s >= (bars[barIdx]?.end ?? Infinity)) barIdx++;
      const bar = bars[barIdx];
      if (!bar) continue;
      const pos = refret(n, tab.tuning, transpose, shiftCapo);
      const slot = Math.min(SLOTS - 1, Math.max(0, Math.floor(((n.start_s - bar.start) / Math.max(bar.end - bar.start, 0.01)) * SLOTS)));
      const line = grid[barIdx]?.[pos ? pos.string - 1 : 0];
      if (line && !line[slot]) line[slot] = pos ? String(pos.fret) : "?";
    }
    const out: { start: number; end: number; text: string }[] = [];
    for (let r = 0; r < bars.length; r += BARS_PER_ROW) {
      const chunk = bars.slice(r, r + BARS_PER_ROW);
      const lines = names.map((name, si) => {
        let line = `${name.padEnd(1)}|`;
        chunk.forEach((_b, bi) => {
          const cells = grid[r + bi]?.[si] ?? [];
          line += cells.map((c) => (c ? c.padEnd(3, "-") : "---")).join("") + "|";
        });
        return line;
      });
      out.push({ start: chunk[0]?.start ?? 0, end: chunk.at(-1)?.end ?? duration, text: lines.join("\n") });
    }
    return out;
  }, [tab, bars, kind, transpose, capo, duration]);

  const job = data?.job ?? null;
  const working = job !== null && ["queued", "analyzing"].includes(job.status);
  const canGenerate = (data?.available_stems.length ?? 0) > 0;

  const generate = async (): Promise<void> => {
    setError(null);
    try {
      await api("POST", `/songs/${song.id}/tabs`);
      setTick((t) => t + 1);
    } catch (e) {
      setError(asApiError(e));
    }
  };

  return (
    <section aria-labelledby="tabs-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="tabs-title" className="text-base font-semibold">
          Tab <span className="text-xs font-normal text-ink-muted">(indicative)</span>
        </h2>
        {(data?.guitar || data?.bass) && (
          <div role="tablist" className="flex rounded-md border border-line p-0.5 text-xs">
            {(["guitar", "bass"] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={kind === k}
                disabled={!data?.[k]}
                onClick={() => setKind(k)}
                className={`rounded px-2.5 py-1 disabled:opacity-40 ${kind === k ? "bg-raised text-ink" : "text-ink-muted"}`}
              >
                {k === "guitar" ? "Chitarra" : "Basso"}
              </button>
            ))}
          </div>
        )}
      </div>
      {error && <Notice tone="error">{error.message}</Notice>}
      {working && (
        <p className="text-xs text-ink-muted" aria-live="polite">
          {job?.message ?? "Generazione delle tab…"} {Math.round((job?.progress ?? 0) * 100)}%
        </p>
      )}
      {job?.status === "failed" && job.error && <Notice tone="error">{job.error.message}</Notice>}
      {!working && !tab && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-ink-muted">
          <p>
            {canGenerate
              ? "Le tab si ricavano dagli stem di chitarra e basso: le note sono rilevate automaticamente e corda e tasto sono stimati."
              : "Per le tab serve prima la separazione in stem."}
          </p>
          {canGenerate && (
            <Button variant="secondary" onClick={() => void generate()} title="La prima volta scarica il modello Basic Pitch (circa 0,7 MB)">
              Genera tab
            </Button>
          )}
        </div>
      )}
      {tab && (
        <>
          <p className="mb-2 text-xs text-ink-muted">
            {kind === "guitar" && capo > 0 ? `Tasti relativi al capo ${capo}. ` : ""}
            {transpose !== 0 ? `Trasposte di ${transpose > 0 ? "+" : ""}${transpose}. ` : ""}
            Clic su una riga per ascoltarla. "?" = nota non suonabile dopo la trasposizione.
          </p>
          <div className="max-h-[28rem] overflow-auto">
            {rows.map((row) => {
              const active = time >= row.start && time < row.end;
              return (
                <pre
                  key={row.start}
                  onClick={() => onSeek(row.start)}
                  className={`mb-2 cursor-pointer rounded px-2 py-1 font-mono text-xs leading-tight ${active ? "bg-accent/10 text-ink" : "text-ink-muted hover:bg-raised"}`}
                >
                  {row.text}
                </pre>
              );
            })}
          </div>
          {!working && canGenerate && (
            <div className="mt-2 flex justify-end">
              <Button variant="ghost" onClick={() => void generate()}>
                Rigenera
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
