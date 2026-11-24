import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { Button, Notice } from "@/components/ui";
import {
  api,
  apiGet,
  asApiError,
  isJobActive,
  type ApiError,
  type ChordEvent,
  type LyricLine,
  type LyricWord,
  type Lyrics,
  type Song,
} from "@/lib/api";
import { formatTimestamp, parseTimestamp } from "@/lib/format";

interface LyricsPanelProps {
  song: Song;
  time: number;
  onSeek: (t: number) => void;
  /** Nome dell'accordo come va mostrato sopra le parole. */
  chordLabel: (c: ChordEvent) => string;
}

type Mode = "karaoke" | "edit";

export function LyricsPanel({ song, time, onSeek, chordLabel }: LyricsPanelProps) {
  const [lyrics, setLyrics] = useState<Lyrics | null>(null);
  const [chords, setChords] = useState<ChordEvent[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [mode, setMode] = useState<Mode>("karaoke");
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    Promise.all([
      apiGet<Lyrics>(`/songs/${song.id}/lyrics`, controller.signal),
      apiGet<ChordEvent[]>(`/songs/${song.id}/chords`, controller.signal).catch(() => []),
    ])
      .then(([l, c]) => {
        setLyrics(l);
        setChords(c.filter((x) => x.chord !== "N"));
        if (isJobActive(l.job)) timer = window.setTimeout(reload, 1500);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(asApiError(e));
      });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [song.id, song.updated_at, tick, reload]);

  /** Esegue un'operazione dell'editor e ricarica; gli errori restano visibili. */
  const run = useCallback(
    async (action: () => Promise<unknown>): Promise<void> => {
      setError(null);
      try {
        await action();
      } catch (e) {
        setError(asApiError(e));
      }
      reload();
    },
    [reload],
  );

  const undo = useCallback(() => void run(() => api("POST", `/songs/${song.id}/undo`)), [run, song.id]);
  const redo = useCallback(() => void run(() => api("POST", `/songs/${song.id}/redo`)), [run, song.id]);

  // Ctrl+Z / Ctrl+Y fuori dai campi di testo (dentro i campi vale l'annulla del browser).
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent): void => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey && lyrics?.can_undo) {
        e.preventDefault();
        undo();
      } else if ((key === "y" || (key === "z" && e.shiftKey)) && lyrics?.can_redo) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lyrics?.can_undo, lyrics?.can_redo, undo, redo]);

  const job = lyrics?.job ?? null;
  const working = isJobActive(job);
  const hasLines = (lyrics?.lines.length ?? 0) > 0;
  const anyEdited = lyrics?.lines.some((l) => l.edited || l.words.some((w) => w.edited)) ?? false;

  return (
    <section aria-labelledby="lyrics-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="lyrics-title" className="text-base font-semibold">
          Testo
        </h2>
        {hasLines && (
          <div className="flex flex-wrap items-center gap-1">
            <div role="tablist" aria-label="Modalità del testo" className="mr-2 flex rounded-md border border-line p-0.5">
              {(["karaoke", "edit"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => setMode(m)}
                  className={`rounded px-2.5 py-1 text-xs ${mode === m ? "bg-raised text-ink" : "text-ink-muted hover:text-ink"}`}
                >
                  {m === "karaoke" ? "Karaoke" : "Modifica"}
                </button>
              ))}
            </div>
            <Button variant="ghost" onClick={undo} disabled={!lyrics?.can_undo} title="Annulla (Ctrl+Z)">
              Annulla
            </Button>
            <Button variant="ghost" onClick={redo} disabled={!lyrics?.can_redo} title="Ripristina (Ctrl+Y)">
              Ripristina
            </Button>
          </div>
        )}
      </div>

      {error && <Notice tone="error">{error.message}</Notice>}
      {!lyrics && !error && <div className="h-24 animate-pulse rounded-md bg-raised" aria-hidden="true" />}

      {lyrics && working && (
        <p className="mb-3 text-xs text-ink-muted" aria-live="polite">
          {job?.message ?? "Elaborazione del testo…"} {Math.round((job?.progress ?? 0) * 100)}%
        </p>
      )}

      {lyrics && !working && <StatusNote lyrics={lyrics} onChanged={reload} />}

      {lyrics && hasLines && mode === "karaoke" && (
        <Karaoke lines={lyrics.lines} chords={chords} chordLabel={chordLabel} time={time} onSeek={onSeek} />
      )}
      {lyrics && hasLines && mode === "edit" && (
        <Editor songId={song.id} lines={lyrics.lines} time={time} onSeek={onSeek} run={run} />
      )}

      {lyrics && !working && (
        <SourceActions
          songId={song.id}
          lyrics={lyrics}
          anyEdited={anyEdited}
          run={run}
        />
      )}
    </section>
  );
}

// ----------------------------------------------------------------- stato

function StatusNote({ lyrics, onChanged }: { lyrics: Lyrics; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const downloadWhisper = async (): Promise<void> => {
    setBusy(true);
    try {
      await api("POST", `/models/${lyrics.whisper.model_id}/download`);
    } finally {
      setBusy(false);
      onChanged();
    }
  };
  const w = lyrics.whisper;
  const whisperAction = !w.installed ? (
    <Button variant="secondary" disabled={busy} onClick={() => void downloadWhisper()}>
      Scarica {w.label} ({w.size_mb} MB)
    </Button>
  ) : undefined;

  const source =
    lyrics.source === "lrclib"
      ? "Testo da LRCLIB"
      : lyrics.source === "transcription"
        ? "Testo trascritto automaticamente dalla voce: controlla e correggi"
        : lyrics.source === "user"
          ? "Testo inserito da te"
          : null;

  switch (lyrics.status) {
    case "instrumental":
      return <Notice tone="info">Brano strumentale: non c'è testo da mostrare.</Notice>;
    case "no_voice":
      return (
        <Notice tone="info">
          Nessuna voce riconosciuta e nessun testo trovato. Puoi incollare il testo qui sotto.
        </Notice>
      );
    case "model_missing":
      return (
        <Notice tone="warn" title="Testo non trovato" action={whisperAction}>
          Per trascrivere la voce serve il modello {w.label}. In alternativa incolla il testo.
        </Notice>
      );
    case "line_synced":
    case "unsynced":
      return (
        <Notice
          tone="warn"
          action={whisperAction}
          title={lyrics.status === "line_synced" ? "Sincronizzato solo per riga" : "Testo non sincronizzato"}
        >
          {source}.{" "}
          {w.installed
            ? "Rilancia la ricerca per allineare parola per parola."
            : `Per l'allineamento parola per parola serve il modello ${w.label}.`}
        </Notice>
      );
    case "aligned":
    case "transcribed":
      return source ? <p className="mb-3 text-xs text-ink-muted">{source}. Allineamento parola per parola automatico: i tempi possono essere imprecisi.</p> : null;
    default:
      return null;
  }
}

function SourceActions({
  songId,
  lyrics,
  anyEdited,
  run,
}: {
  songId: string;
  lyrics: Lyrics;
  anyEdited: boolean;
  run: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const [confirmRestore, setConfirmRestore] = useState(false);
  const hasLines = lyrics.lines.length > 0;

  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-line pt-3">
      {pasting ? (
        <div className="flex flex-col gap-2">
          <label htmlFor="paste-lyrics" className="text-xs text-ink-muted">
            Incolla il testo (una riga per verso; accetta anche il formato LRC con i tempi).
            {hasLines ? " Sostituirà il testo attuale e le modifiche." : ""}
          </label>
          <textarea
            id="paste-lyrics"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            className="rounded-md border border-line bg-ground px-2.5 py-2 font-mono text-xs focus:border-brand focus:outline-none"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPasting(false)}>
              Annulla
            </Button>
            <Button
              variant="primary"
              disabled={!text.trim()}
              onClick={() => {
                setPasting(false);
                void run(() => api("POST", `/songs/${songId}/lyrics/refresh`, { text, search: false }));
              }}
            >
              Usa e allinea
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          {anyEdited &&
            (confirmRestore ? (
              <>
                <span className="self-center text-xs text-ink-muted">Annullare tutte le modifiche al testo?</span>
                <Button variant="ghost" onClick={() => setConfirmRestore(false)}>
                  No
                </Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    setConfirmRestore(false);
                    void run(() => api("POST", `/songs/${songId}/lyrics/restore`));
                  }}
                >
                  Ripristina originale
                </Button>
              </>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmRestore(true)}>
                Ripristina originale
              </Button>
            ))}
          {lyrics.lrclib_enabled && (
            <Button
              variant="ghost"
              title={hasLines ? "Sostituisce il testo attuale" : undefined}
              onClick={() => void run(() => api("POST", `/songs/${songId}/lyrics/refresh`, { search: true }))}
            >
              {hasLines ? "Cerca e allinea di nuovo" : "Cerca il testo"}
            </Button>
          )}
          <Button variant="secondary" onClick={() => setPasting(true)}>
            Incolla il testo
          </Button>
        </div>
      )}
      {!lyrics.lrclib_enabled && (
        <p className="text-xs text-ink-muted">
          La ricerca online dei testi (LRCLIB) è disattivata: LOCALCHORDS_LRCLIB_ENABLED.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- karaoke

function chordsByWord(line: LyricLine, chords: ChordEvent[], label: (c: ChordEvent) => string): Map<string, string> {
  const map = new Map<string, string>();
  const timed = line.words.filter((w) => w.start_s !== null);
  if (line.start_s === null || timed.length === 0) return map;
  const lineEnd = line.end_s ?? Infinity;
  for (const c of chords) {
    if (c.start_s < line.start_s - 0.3 || c.start_s >= lineEnd) continue;
    // la parola che inizia per ultima prima del cambio d'accordo (o la prima della riga)
    let target = timed[0];
    for (const w of timed) if ((w.start_s ?? 0) <= c.start_s + 0.15) target = w;
    if (target && !map.has(target.id)) map.set(target.id, label(c));
  }
  return map;
}

function Karaoke({
  lines,
  chords,
  chordLabel,
  time,
  onSeek,
}: {
  lines: LyricLine[];
  chords: ChordEvent[];
  chordLabel: (c: ChordEvent) => string;
  time: number;
  onSeek: (t: number) => void;
}) {
  const [follow, setFollow] = useState(true);
  const activeRef = useRef<HTMLLIElement | null>(null);
  const activeIdx = useMemo(() => {
    let idx = -1;
    lines.forEach((l, i) => {
      if (l.start_s !== null && l.start_s <= time + 0.05) idx = i;
    });
    return idx;
  }, [lines, time]);
  const chordMaps = useMemo(() => lines.map((l) => chordsByWord(l, chords, chordLabel)), [lines, chords, chordLabel]);

  useEffect(() => {
    if (follow) activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIdx, follow]);

  return (
    <div>
      <label className="mb-2 flex items-center justify-end gap-2 text-xs text-ink-muted">
        <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} className="accent-[var(--brand)]" />
        Scorri automaticamente
      </label>
      <ol className="flex max-h-[28rem] flex-col gap-3 overflow-y-auto pr-2" aria-label="Testo sincronizzato">
        {lines.map((line, i) => {
          const active = i === activeIdx;
          const chordMap = chordMaps[i] ?? new Map<string, string>();
          return (
            <li
              key={line.id}
              ref={active ? activeRef : undefined}
              aria-current={active ? "true" : undefined}
              className={`flex flex-wrap gap-x-1.5 rounded-md px-2 py-1 transition-colors ${active ? "bg-raised" : ""} ${!active && line.start_s !== null && line.start_s > time ? "text-ink-muted" : ""}`}
            >
              {line.words.length === 0 && <span className="pt-4 text-base">{line.text}</span>}
              {line.words.map((w) => (
                <WordChip key={w.id} word={w} chord={chordMap.get(w.id) ?? null} time={time} activeLine={active} onSeek={onSeek} />
              ))}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function WordChip({
  word,
  chord,
  time,
  activeLine,
  onSeek,
}: {
  word: LyricWord;
  chord: string | null;
  time: number;
  activeLine: boolean;
  onSeek: (t: number) => void;
}) {
  const sung = word.start_s !== null && word.start_s <= time;
  const current = sung && word.end_s !== null && time < word.end_s;
  return (
    <button
      type="button"
      disabled={word.start_s === null}
      onClick={() => word.start_s !== null && onSeek(word.start_s)}
      className="flex flex-col items-start text-left disabled:cursor-default"
    >
      <span className="h-4 font-mono text-xs font-semibold text-brand" aria-hidden={chord ? undefined : "true"}>
        {chord ?? ""}
      </span>
      <span
        className={`rounded px-0.5 text-base ${current ? "bg-brand text-on-brand" : activeLine && sung ? "text-brand" : ""}`}
      >
        {word.text}
      </span>
    </button>
  );
}

// ----------------------------------------------------------------- editor

type Run = (action: () => Promise<unknown>) => Promise<void>;

function TimeInput({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number | null;
  onCommit: (v: number | null) => void;
}) {
  const [text, setText] = useState(formatTimestamp(value));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => setText(formatTimestamp(value)), [value]);
  const commit = (): void => {
    const parsed = parseTimestamp(text);
    if (parsed === undefined) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (parsed !== value) onCommit(parsed);
  };
  return (
    <input
      aria-label={label}
      aria-invalid={invalid}
      value={text}
      placeholder="m:ss.cc"
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => e.key === "Enter" && commit()}
      className={`w-20 rounded border bg-ground px-1.5 py-0.5 font-mono text-xs focus:outline-none ${invalid ? "border-bad" : "border-line focus:border-brand"}`}
    />
  );
}

function Editor({
  songId,
  lines,
  time,
  onSeek,
  run,
}: {
  songId: string;
  lines: LyricLine[];
  time: number;
  onSeek: (t: number) => void;
  run: Run;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const patchLine = (id: string, body: Record<string, unknown>): void =>
    void run(() => api("PATCH", `/songs/${songId}/lyrics/${id}`, body));

  return (
    <ol className="flex flex-col gap-1" aria-label="Editor del testo">
      <li className="flex justify-end">
        <Button
          variant="ghost"
          onClick={() => void run(() => api("POST", `/songs/${songId}/lyrics/lines`, { after_line_id: null, text: "Nuova riga" }))}
        >
          + Riga all'inizio
        </Button>
      </li>
      {lines.map((line, i) => (
        <li key={line.id} className={`rounded-md border px-2 py-1.5 ${line.edited ? "border-brand/40" : "border-line"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <TimeInput label={`Inizio riga ${i + 1}`} value={line.start_s} onCommit={(v) => patchLine(line.id, { start_s: v })} />
            <Button
              variant="ghost"
              aria-label="Imposta l'inizio alla posizione di ascolto" title="Imposta l'inizio alla posizione di ascolto"
              className="px-1.5 py-0.5 text-xs"
              onClick={() => patchLine(line.id, { start_s: Math.round(time * 100) / 100 })}
            >
              ⏱
            </Button>
            <LineText line={line} onCommit={(text) => patchLine(line.id, { text })} />
            <TimeInput label={`Fine riga ${i + 1}`} value={line.end_s} onCommit={(v) => patchLine(line.id, { end_s: v })} />
            <span className="flex gap-0.5">
              <Button variant="ghost" className="px-1.5 py-0.5 text-xs" disabled={line.start_s === null} onClick={() => line.start_s !== null && onSeek(line.start_s)} aria-label="Ascolta da qui" title="Ascolta da qui">
                ▶
              </Button>
              <Button variant="ghost" className="px-1.5 py-0.5 text-xs" onClick={() => setOpen(open === line.id ? null : line.id)} aria-expanded={open === line.id}>
                Parole
              </Button>
              <Button
                variant="ghost"
                className="px-1.5 py-0.5 text-xs"
                aria-label="Aggiungi una riga dopo" title="Aggiungi una riga dopo"
                onClick={() =>
                  void run(() =>
                    api("POST", `/songs/${songId}/lyrics/lines`, {
                      after_line_id: line.id,
                      text: "Nuova riga",
                      start_s: line.end_s,
                    }),
                  )
                }
              >
                +
              </Button>
              {line.edited && (
                <Button variant="ghost" className="px-1.5 py-0.5 text-xs" aria-label="Ripristina l'originale" title="Ripristina l'originale" onClick={() => void run(() => api("POST", `/songs/${songId}/lyrics/${line.id}/restore`))}>
                  ↺
                </Button>
              )}
              <Button variant="ghost" className="px-1.5 py-0.5 text-xs text-bad" aria-label="Elimina la riga" title="Elimina la riga" onClick={() => void run(() => api("DELETE", `/songs/${songId}/lyrics/${line.id}`))}>
                ✕
              </Button>
            </span>
          </div>
          {open === line.id && <WordsEditor songId={songId} line={line} run={run} />}
        </li>
      ))}
    </ol>
  );
}

function LineText({ line, onCommit }: { line: LyricLine; onCommit: (text: string) => void }) {
  const [text, setText] = useState(line.text);
  useEffect(() => setText(line.text), [line.text]);
  const commit = (): void => {
    const clean = text.trim();
    if (clean && clean !== line.text) onCommit(clean);
    else setText(line.text);
  };
  return (
    <input
      aria-label="Testo della riga"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      className="min-w-0 flex-1 rounded border border-line bg-ground px-2 py-0.5 focus:border-brand focus:outline-none"
    />
  );
}

function WordsEditor({ songId, line, run }: { songId: string; line: LyricLine; run: Run }) {
  const patch = (id: string, body: Record<string, unknown>): void =>
    void run(() => api("PATCH", `/songs/${songId}/lyrics/words/${id}`, body));
  return (
    <ul className="mt-2 flex flex-col gap-1 border-l border-line pl-3" aria-label={`Parole della riga ${line.text}`}>
      {line.words.map((w) => (
        <li key={w.id} className="flex flex-wrap items-center gap-2 text-xs">
          <TimeInput label={`Inizio di ${w.text}`} value={w.start_s} onCommit={(v) => patch(w.id, { start_s: v })} />
          <WordText word={w} onCommit={(text) => patch(w.id, { text })} />
          <TimeInput label={`Fine di ${w.text}`} value={w.end_s} onCommit={(v) => patch(w.id, { end_s: v })} />
          {w.confidence !== null && w.confidence < 0.3 && !w.edited && (
            <span className="text-warn" title="Tempo incerto o stimato">incerto</span>
          )}
          <Button
            variant="ghost"
            className="px-1.5 py-0.5 text-xs"
            aria-label="Aggiungi una parola dopo" title="Aggiungi una parola dopo"
            onClick={() =>
              void run(() => api("POST", `/songs/${songId}/lyrics/${line.id}/words`, { after_word_id: w.id, text: "…" }))
            }
          >
            +
          </Button>
          <Button
            variant="ghost"
            className="px-1.5 py-0.5 text-xs text-bad"
            aria-label="Elimina la parola" title="Elimina la parola"
            onClick={() => void run(() => api("DELETE", `/songs/${songId}/lyrics/words/${w.id}`))}
          >
            ✕
          </Button>
        </li>
      ))}
    </ul>
  );
}

function WordText({ word, onCommit }: { word: LyricWord; onCommit: (text: string) => void }) {
  const [text, setText] = useState(word.text);
  useEffect(() => setText(word.text), [word.text]);
  const commit = (): void => {
    const clean = text.trim();
    if (clean && clean !== word.text && !/\s/.test(clean)) onCommit(clean);
    else setText(word.text);
  };
  return (
    <input
      aria-label="Parola"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      className="w-32 rounded border border-line bg-ground px-1.5 py-0.5 focus:border-brand focus:outline-none"
    />
  );
}
