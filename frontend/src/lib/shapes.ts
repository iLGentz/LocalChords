/**
 * Diteggiature di chitarra e ukulele da chords-db (MIT), caricate su richiesta, e
 * suggerimento del capo che riduce barré e posizioni alte.
 */
import { parseChord, type ParsedChord } from "@/lib/music";

export type FrettedInstrument = "guitar" | "ukulele";

export interface Position {
  frets: number[];
  fingers: number[];
  baseFret: number;
  barres: number[];
  capo?: boolean;
}

interface ChordEntry {
  key: string;
  suffix: string;
  positions: Position[];
}

interface ChordsDb {
  main: { strings: number; fretsOnChord: number };
  chords: Record<string, ChordEntry[]>;
}

const cache: Partial<Record<FrettedInstrument, Promise<ChordsDb>>> = {};

export function loadDb(instrument: FrettedInstrument): Promise<ChordsDb> {
  cache[instrument] ??=
    instrument === "guitar"
      ? import("@tombatossals/chords-db/lib/guitar.json").then((m) => m.default as unknown as ChordsDb)
      : import("@tombatossals/chords-db/lib/ukulele.json").then((m) => m.default as unknown as ChordsDb);
  return cache[instrument];
}

const NAMES: Record<number, string[]> = {
  0: ["C"], 1: ["Csharp", "C#", "Db"], 2: ["D"], 3: ["Eb", "Dsharp", "D#"], 4: ["E"], 5: ["F"],
  6: ["Fsharp", "F#", "Gb"], 7: ["G"], 8: ["Ab", "Gsharp", "G#"], 9: ["A"], 10: ["Bb", "Asharp", "A#"], 11: ["B"],
};
const BASS_NAMES: Record<number, string[]> = {
  0: ["C"], 1: ["C#", "Db"], 2: ["D"], 3: ["D#", "Eb"], 4: ["E"], 5: ["F"], 6: ["F#", "Gb"], 7: ["G"],
  8: ["G#", "Ab"], 9: ["A"], 10: ["Bb", "A#"], 11: ["B"],
};

function dbSuffix(p: ParsedChord): string {
  return p.suffix === "" ? "major" : p.suffix === "m" ? "minor" : p.suffix;
}

export function findPositions(db: ChordsDb, shape: string): Position[] {
  const p = parseChord(shape);
  if (!p) return [];
  const key = (NAMES[p.root] ?? []).find((k) => k in db.chords);
  if (!key) return [];
  const entries = db.chords[key] ?? [];
  const base = dbSuffix(p);
  if (p.bass !== null && p.bass !== p.root) {
    const prefix = p.suffix === "m" ? "m/" : p.suffix === "" ? "/" : null;
    if (prefix) {
      for (const bassName of BASS_NAMES[p.bass] ?? []) {
        const hit = entries.find((e) => e.suffix === prefix + bassName);
        if (hit) return hit.positions;
      }
    }
  }
  return entries.find((e) => e.suffix === base)?.positions ?? [];
}

/** Difficoltà di una diteggiatura: barré, posizione alta, estensione delle dita. */
export function difficulty(pos: Position): number {
  const fretted = pos.frets.filter((f) => f > 0);
  const span = fretted.length ? Math.max(...fretted) - Math.min(...fretted) : 0;
  return pos.barres.length * 3 + (pos.baseFret > 1 ? 1.5 : 0) + span * 0.5 + fretted.length * 0.2;
}

export function easiest(positions: Position[]): Position | null {
  return positions.reduce<Position | null>((best, p) => (best === null || difficulty(p) < difficulty(best) ? p : best), null);
}

export interface CapoSuggestion {
  capo: number;
  score: number;
  barres: number;
}

/**
 * Valuta i capo da 0 a 7 per le forme sonanti indicate (accordo, durata in secondi) e li
 * restituisce dal più comodo. `barres` conta i secondi di accordi con barré.
 */
export function suggestCapo(
  db: ChordsDb,
  sounding: { symbol: string; duration: number }[],
): CapoSuggestion[] {
  const out: CapoSuggestion[] = [];
  for (let capo = 0; capo <= 7; capo++) {
    let score = 0;
    let barres = 0;
    for (const { symbol, duration } of sounding) {
      const p = parseChord(symbol);
      if (!p) continue;
      const shifted = `${(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const)[(p.root - capo + 12) % 12]}${p.suffix}`;
      const pos = easiest(findPositions(db, shifted));
      const d = pos ? difficulty(pos) : 6;
      score += d * duration;
      if (pos && pos.barres.length > 0) barres += duration;
    }
    out.push({ capo, score: score + capo * 2, barres });
  }
  return out.sort((a, b) => a.score - b.score);
}
