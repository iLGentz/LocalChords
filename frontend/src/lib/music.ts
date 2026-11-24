/**
 * Teoria musicale per la visualizzazione: trasposizione, capo, semplificazione e notazioni.
 *
 * Gli accordi arrivano dal backend nella forma canonica con i diesis (`C#m7`, `F#/A#`).
 * Qui si applicano, in quest'ordine: semplificazione → trasposizione → capo (forme da
 * suonare) → notazione. La grafia (diesis o bemolle) segue la tonalità risultante.
 */
import { Chord, Key } from "@tonaljs/tonal";

export type Notation = "american" | "italian" | "numeric";
export type SimplifyLevel = "original" | "intermediate" | "easy";

const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const;
const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"] as const;
const MAJOR_KEYS = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"] as const;
const MINOR_KEYS = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"] as const;
const ITALIAN: Record<string, string> = { C: "Do", D: "Re", E: "Mi", F: "Fa", G: "Sol", A: "La", B: "Si" };
const DEGREES = ["1", "b2", "2", "b3", "3", "4", "b5", "5", "b6", "6", "b7", "7"] as const;

export interface ParsedChord {
  root: number;
  suffix: string;
  bass: number | null;
}

export function noteIndex(name: string): number | null {
  const letter = name[0];
  if (!letter) return null;
  const base = (SHARPS as readonly string[]).indexOf(letter);
  if (base < 0) return null;
  let idx = base;
  for (const ch of name.slice(1)) {
    if (ch === "#") idx += 1;
    else if (ch === "b") idx -= 1;
    else break;
  }
  return ((idx % 12) + 12) % 12;
}

const CHORD_RE = /^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/;

export function parseChord(symbol: string): ParsedChord | null {
  const m = CHORD_RE.exec(symbol.trim());
  if (!m || !m[1]) return null;
  const root = noteIndex(m[1]);
  if (root === null) return null;
  const bass = m[3] ? noteIndex(m[3]) : null;
  return { root, suffix: m[2] ?? "", bass };
}

function noteName(index: number, flats: boolean): string {
  const i = ((index % 12) + 12) % 12;
  return (flats ? FLATS : SHARPS)[i] ?? "C";
}

export function formatChord(p: ParsedChord, flats: boolean): string {
  const base = noteName(p.root, flats) + p.suffix;
  return p.bass !== null && p.bass !== p.root ? `${base}/${noteName(p.bass, flats)}` : base;
}

// ------------------------------------------------------------------- tonalità

export interface KeyInfo {
  tonic: number;
  minor: boolean;
}

export function parseKey(key: string | null): KeyInfo | null {
  if (!key) return null;
  const minor = key.endsWith("m");
  const tonic = noteIndex(minor ? key.slice(0, -1) : key);
  return tonic === null ? null : { tonic, minor };
}

export function keyName(k: KeyInfo): string {
  return (k.minor ? MINOR_KEYS : MAJOR_KEYS)[((k.tonic % 12) + 12) % 12] ?? "C";
}

export function transposeKey(k: KeyInfo, semitones: number): KeyInfo {
  return { tonic: (k.tonic + semitones + 120) % 12, minor: k.minor };
}

/** Vero se la tonalità si scrive con i bemolle (Tonal.js: alterazioni dell'armatura). */
export function prefersFlats(k: KeyInfo | null): boolean {
  if (!k) return false;
  const name = keyName(k);
  const alteration = k.minor ? Key.minorKey(name.slice(0, -1)).alteration : Key.majorKey(name).alteration;
  return alteration < 0;
}

// -------------------------------------------------------------- semplificazione

export interface Simplified {
  chord: ParsedChord;
  reason: string | null;
}

const INTERMEDIATE: Record<string, [string, string]> = {
  maj7: ["", "La settima maggiore è un colore: la triade maggiore mantiene la stessa funzione."],
  sus4: ["", "Accordo sospeso: la terza maggiore sostituisce la quarta."],
  sus2: ["", "Accordo sospeso: la terza maggiore sostituisce la seconda."],
  aug: ["", "L'accordo aumentato diventa la triade maggiore sulla stessa fondamentale."],
};
const EASY: Record<string, [string, string]> = {
  ...INTERMEDIATE,
  "7": ["", "La settima di dominante si può omettere: resta la triade maggiore."],
  m7: ["m", "La settima minore si può omettere: resta la triade minore."],
  dim: ["m", "La triade diminuita è sostituita dalla minore sulla stessa fondamentale (più semplice, meno tesa)."],
};

export function simplify(p: ParsedChord, level: SimplifyLevel): Simplified {
  if (level === "original") return { chord: p, reason: null };
  const table = level === "easy" ? EASY : INTERMEDIATE;
  const reasons: string[] = [];
  let suffix = p.suffix;
  const rule = table[suffix];
  if (rule) {
    suffix = rule[0];
    reasons.push(rule[1]);
  }
  let bass = p.bass;
  if (bass !== null && bass !== p.root) {
    bass = null;
    reasons.push("Il basso del rivolto è omesso: si suona lo stesso accordo in posizione fondamentale.");
  }
  return { chord: { root: p.root, suffix, bass }, reason: reasons.length ? reasons.join(" ") : null };
}

// ------------------------------------------------------------------ notazioni

export function formatNotation(p: ParsedChord, notation: Notation, flats: boolean, key: KeyInfo | null): string {
  if (notation === "numeric" && key) {
    const degree = DEGREES[(p.root - key.tonic + 12) % 12] ?? "?";
    const bass = p.bass !== null && p.bass !== p.root ? `/${DEGREES[(p.bass - key.tonic + 12) % 12] ?? "?"}` : "";
    return `${degree}${p.suffix}${bass}`;
  }
  const name = formatChord(p, flats);
  if (notation !== "italian") return name;
  return name.replace(/([A-G])([#b]?)/g, (_m, letter: string, acc: string) => `${ITALIAN[letter] ?? letter}${acc}`);
}

// --------------------------------------------------------------- visualizzazione

export interface ViewSettings {
  transpose: number;
  capo: number;
  simplification: SimplifyLevel;
  notation: Notation;
  key: string | null;
}

export interface DisplayedChord {
  /** Testo mostrato (notazione scelta, dopo semplificazione, trasposizione e capo). */
  label: string;
  /** Forma in notazione americana, per i diagrammi. */
  shape: string;
  /** Accordo originale se diverso da quello mostrato. */
  original: string | null;
  /** Spiegazione se è stato semplificato. */
  simplifiedReason: string | null;
}

export function displayChord(symbol: string, view: ViewSettings, exempt = false): DisplayedChord | null {
  const parsed = parseChord(symbol);
  if (!parsed) return null;
  const baseKey = parseKey(view.key);
  const soundingKey = baseKey ? transposeKey(baseKey, view.transpose) : null;
  const shapeKey = soundingKey ? transposeKey(soundingKey, -view.capo) : null;
  const flats = prefersFlats(shapeKey);
  const simplified = exempt ? { chord: parsed, reason: null } : simplify(parsed, view.simplification);
  const shift = view.transpose - view.capo;
  const moved: ParsedChord = {
    root: (simplified.chord.root + shift + 120) % 12,
    suffix: simplified.chord.suffix,
    bass: simplified.chord.bass === null ? null : (simplified.chord.bass + shift + 120) % 12,
  };
  const label = formatNotation(moved, view.notation, flats, shapeKey);
  const shape = formatChord(moved, flats);
  const originalText = formatChord(parsed, prefersFlats(baseKey));
  return {
    label,
    shape,
    original: originalText !== shape || view.notation !== "american" ? originalText : null,
    simplifiedReason: simplified.reason,
  };
}

/** Note dell'accordo (Tonal.js), per il diagramma del pianoforte. */
export function chordNotes(shape: string): number[] {
  const p = parseChord(shape);
  if (!p) return [];
  const tonic = noteName(p.root, false);
  const notes = Chord.get(`${tonic}${p.suffix === "" ? "M" : p.suffix}`).notes;
  const out = notes.map((n) => noteIndex(n)).filter((n): n is number => n !== null);
  if (p.bass !== null && !out.includes(p.bass)) out.unshift(p.bass);
  return out;
}
