import { useEffect, useState } from "react";

import { chordNotes } from "@/lib/music";
import { easiest, findPositions, loadDb, type FrettedInstrument, type Position } from "@/lib/shapes";

export type DiagramInstrument = FrettedInstrument | "piano";

interface ChordDiagramsProps {
  /** Forme in notazione americana (dopo trasposizione e capo), in ordine di apparizione. */
  shapes: { shape: string; label: string }[];
  instrument: DiagramInstrument;
  activeShape: string | null;
}

/** Diagrammi degli accordi del brano per chitarra, ukulele o pianoforte. */
export function ChordDiagrams({ shapes, instrument, activeShape }: ChordDiagramsProps) {
  const [db, setDb] = useState<Awaited<ReturnType<typeof loadDb>> | null>(null);

  useEffect(() => {
    if (instrument === "piano") return;
    let alive = true;
    setDb(null);
    void loadDb(instrument).then((d) => alive && setDb(d));
    return () => {
      alive = false;
    };
  }, [instrument]);

  return (
    <ul className="flex flex-wrap gap-3" aria-label="Diagrammi degli accordi">
      {shapes.map(({ shape, label }) => {
        const active = shape === activeShape;
        const position = instrument !== "piano" && db ? easiest(findPositions(db, shape)) : null;
        return (
          <li
            key={shape}
            className={`flex w-28 flex-col items-center rounded-md border px-2 pb-2 pt-1 ${active ? "border-brand bg-brand/10" : "border-line"}`}
          >
            <span className="font-mono text-sm font-semibold">{label}</span>
            {instrument === "piano" ? (
              <PianoDiagram notes={chordNotes(shape)} label={label} />
            ) : position ? (
              <FretDiagram position={position} strings={instrument === "guitar" ? 6 : 4} label={label} />
            ) : (
              <span className="py-6 text-center text-xs text-ink-muted">{db ? "diagramma non disponibile" : "…"}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function FretDiagram({ position, strings, label }: { position: Position; strings: number; label: string }) {
  const frets = 4;
  const w = 88;
  const h = 100;
  const left = 12;
  const top = 18;
  const gapX = (w - left * 2) / (strings - 1);
  const gapY = (h - top - 8) / frets;
  const x = (s: number): number => left + s * gapX;
  const y = (f: number): number => top + f * gapY;
  const description = position.frets
    .map((f, s) => `corda ${strings - s}: ${f < 0 ? "non suonata" : f === 0 ? "a vuoto" : `tasto ${f + position.baseFret - 1}`}`)
    .join(", ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label={`${label}: ${description}`}>
      {position.baseFret === 1 ? (
        <rect x={left} y={top - 3} width={w - left * 2} height={3} fill="var(--ink)" />
      ) : (
        <text x={1} y={y(0.6)} fontSize={9} fill="var(--ink-muted)">
          {position.baseFret}
        </text>
      )}
      {Array.from({ length: frets + 1 }, (_, f) => (
        <line key={`f${f}`} x1={left} x2={w - left} y1={y(f)} y2={y(f)} stroke="var(--line)" />
      ))}
      {Array.from({ length: strings }, (_, s) => (
        <line key={`s${s}`} x1={x(s)} x2={x(s)} y1={top} y2={y(frets)} stroke="var(--ink-muted)" strokeWidth={0.8} />
      ))}
      {position.barres.map((b) => {
        const covered = position.frets.map((f, s) => (f === b ? s : -1)).filter((s) => s >= 0);
        if (covered.length < 2) return null;
        return (
          <rect
            key={`b${b}`}
            x={x(Math.min(...covered)) - 4}
            y={y(b - 0.5) - 4}
            width={x(Math.max(...covered)) - x(Math.min(...covered)) + 8}
            height={8}
            rx={4}
            fill="var(--brand)"
          />
        );
      })}
      {position.frets.map((f, s) =>
        f < 0 ? (
          <text key={`m${s}`} x={x(s)} y={top - 6} fontSize={8} textAnchor="middle" fill="var(--ink-muted)">
            ×
          </text>
        ) : f === 0 ? (
          <circle key={`o${s}`} cx={x(s)} cy={top - 8} r={2.5} fill="none" stroke="var(--ink-muted)" />
        ) : (
          <g key={`d${s}`}>
            <circle cx={x(s)} cy={y(f - 0.5)} r={4.5} fill="var(--brand)" />
            {(position.fingers[s] ?? 0) > 0 && (
              <text x={x(s)} y={y(f - 0.5) + 3} fontSize={7} textAnchor="middle" fill="var(--on-brand)" fontWeight={700}>
                {position.fingers[s]}
              </text>
            )}
          </g>
        ),
      )}
    </svg>
  );
}

const WHITE = [0, 2, 4, 5, 7, 9, 11];
const BLACK = [1, 3, 6, 8, 10];
const BLACK_POS: Record<number, number> = { 1: 0, 3: 1, 6: 3, 8: 4, 10: 5 };

function PianoDiagram({ notes, label }: { notes: number[]; label: string }) {
  const keyW = 7;
  const w = keyW * 14;
  const h = 52;
  const on = new Set(notes);
  const bass = notes[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label={`${label}: note ${notes.length}`} className="mt-2">
      {[0, 1].flatMap((oct) =>
        WHITE.map((pc, i) => (
          <rect
            key={`w${oct}-${pc}`}
            x={(oct * 7 + i) * keyW}
            y={0}
            width={keyW}
            height={h}
            fill={on.has(pc) && (oct === 0 ? pc === bass : pc !== bass || notes.length === 1) ? "var(--brand)" : "#ece7e0"}
            stroke="#3a3631"
          />
        )),
      )}
      {[0, 1].flatMap((oct) =>
        BLACK.map((pc) => (
          <rect
            key={`b${oct}-${pc}`}
            x={(oct * 7 + (BLACK_POS[pc] ?? 0) + 1) * keyW - keyW * 0.3}
            y={0}
            width={keyW * 0.6}
            height={h * 0.6}
            fill={on.has(pc) && (oct === 0 ? pc === bass : pc !== bass || notes.length === 1) ? "var(--brand)" : "#1c1a18"}
          />
        )),
      )}
    </svg>
  );
}
