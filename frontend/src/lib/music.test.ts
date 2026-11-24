import { describe, expect, it } from "vitest";

import { formatDuration, formatTimestamp, parseTimestamp } from "@/lib/format";
import {
  chordNotes,
  displayChord,
  formatNotation,
  parseChord,
  parseKey,
  prefersFlats,
  simplify,
  type ViewSettings,
} from "@/lib/music";
import { difficulty, easiest, findPositions, loadDb, suggestCapo } from "@/lib/shapes";

const base: ViewSettings = { transpose: 0, capo: 0, simplification: "original", notation: "american", key: "C" };
const show = (symbol: string, v: Partial<ViewSettings> = {}) => displayChord(symbol, { ...base, ...v });

describe("parsing", () => {
  it("riconosce fondamentale, suffisso e basso", () => {
    expect(parseChord("C#m7/G#")).toEqual({ root: 1, suffix: "m7", bass: 8 });
    expect(parseChord("Bb")).toEqual({ root: 10, suffix: "", bass: null });
    expect(parseChord("H")).toBeNull();
  });
});

describe("trasposizione", () => {
  it("copre da -11 a +11 tornando all'originale con 12", () => {
    for (let t = -11; t <= 11; t++) expect(show("C", { transpose: t })?.shape).toBeTruthy();
    expect(show("Am", { transpose: 2 })?.shape).toBe("Bm");
    expect(show("G7", { transpose: -2 })?.shape).toBe("F7");
  });

  it("usa i bemolle nelle tonalità con i bemolle e i diesis nelle altre", () => {
    expect(show("C", { transpose: 3 })?.shape).toBe("Eb"); // Do → Mib maggiore
    expect(show("C", { transpose: 1, key: "C" })?.shape).toBe("Db");
    expect(show("C", { transpose: 6, key: "C" })?.shape).toBe("F#");
    expect(show("A", { transpose: 2, key: "A" })?.shape).toBe("B"); // La → Si: diesis
    expect(prefersFlats(parseKey("F"))).toBe(true);
    expect(prefersFlats(parseKey("Ebm"))).toBe(true);
    expect(prefersFlats(parseKey("E"))).toBe(false);
  });

  it("traspone anche il basso dei rivolti e mostra l'originale", () => {
    const d = show("C/E", { transpose: 2 });
    expect(d?.shape).toBe("D/F#");
    expect(d?.original).toBe("C/E");
    expect(show("C")?.original).toBeNull();
  });
});

describe("capo", () => {
  it("mostra le forme da suonare", () => {
    // brano in Re suonato con capo 2: forme di Do
    expect(show("D", { key: "D", capo: 2 })?.shape).toBe("C");
    expect(show("Bm", { key: "D", capo: 2 })?.shape).toBe("Am");
    // trasposizione e capo insieme
    expect(show("C", { transpose: 2, capo: 2 })?.shape).toBe("C");
  });
});

describe("semplificazione", () => {
  it("livello intermedio: maj7, sus, aug e rivolti diventano triadi; 7 e m7 restano", () => {
    const p = parseChord("Cmaj7");
    expect(p && simplify(p, "intermediate").chord.suffix).toBe("");
    expect(show("Csus4", { simplification: "intermediate" })?.shape).toBe("C");
    expect(show("G7", { simplification: "intermediate" })?.shape).toBe("G7");
    expect(show("C/E", { simplification: "intermediate" })?.shape).toBe("C");
  });

  it("livello facile: tutto maggiore o minore, con spiegazione", () => {
    const d = show("Am7", { simplification: "easy" });
    expect(d?.shape).toBe("Am");
    expect(d?.simplifiedReason).toMatch(/settima/);
    expect(show("Bdim", { simplification: "easy" })?.shape).toBe("Bm");
    expect(show("G7", { simplification: "easy" })?.shape).toBe("G");
    expect(show("C", { simplification: "easy" })?.simplifiedReason).toBeNull();
  });

  it("un accordo esentato non viene semplificato", () => {
    expect(displayChord("Am7", { ...base, simplification: "easy" }, true)?.shape).toBe("Am7");
  });
});

describe("notazioni", () => {
  it("italiana e numerica", () => {
    expect(show("C#m7", { notation: "italian", key: "E" })?.label).toBe("Do#m7");
    expect(show("Bb/D", { notation: "italian", key: "F" })?.label).toBe("Sib/Re");
    const key = parseKey("C");
    const am = parseChord("Am");
    expect(am && formatNotation(am, "numeric", false, key)).toBe("6m");
    expect(show("G7", { notation: "numeric" })?.label).toBe("57");
    expect(show("F/A", { notation: "numeric" })?.label).toBe("4/6");
  });
});

describe("pianoforte", () => {
  it("note dell'accordo con Tonal.js", () => {
    expect(chordNotes("C")).toEqual([0, 4, 7]);
    expect(chordNotes("Am7")).toEqual([9, 0, 4, 7]);
    expect(chordNotes("C/E")[0]).toBe(0);
  });
});

describe("diagrammi e capo suggerito (chords-db)", () => {
  it("trova diteggiature per chitarra e ukulele, anche per i rivolti", async () => {
    const guitar = await loadDb("guitar");
    const c = easiest(findPositions(guitar, "C"));
    expect(c?.frets).toEqual([-1, 3, 2, 0, 1, 0]);
    const fsm = findPositions(guitar, "F#m");
    expect(fsm.some((p) => p.barres.length > 0)).toBe(true); // i barré sono letti dai dati
    const chosen = easiest(fsm);
    expect(chosen && fsm.every((p) => difficulty(chosen) <= difficulty(p))).toBe(true);
    expect(findPositions(guitar, "C/E").length).toBeGreaterThan(0);
    const uke = await loadDb("ukulele");
    expect(findPositions(uke, "Db").length).toBeGreaterThan(0);
    expect(findPositions(uke, "C#").length).toBeGreaterThan(0);
  });

  it("per un brano in Mib suggerisce un capo che evita i barré", async () => {
    const guitar = await loadDb("guitar");
    const sounding = ["Eb", "Bb", "Cm", "Ab"].map((symbol) => ({ symbol, duration: 10 }));
    const [best] = suggestCapo(guitar, sounding);
    expect(best?.capo).not.toBe(0);
    expect(best?.barres).toBeLessThan(suggestCapo(guitar, sounding).find((s) => s.capo === 0)!.barres);
  });
});

describe("formattazione", () => {
  it("tempi", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(65)).toBe("1:05");
    expect(formatTimestamp(65.5)).toBe("1:05.50");
    expect(parseTimestamp("1:05.5")).toBe(65.5);
    expect(parseTimestamp("12,25")).toBe(12.25);
    expect(parseTimestamp("")).toBeNull();
    expect(parseTimestamp("1:75")).toBeUndefined();
    expect(parseTimestamp("abc")).toBeUndefined();
  });
});
