import type { JobStatus, SongStatus } from "@/lib/api";

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mmss = `${h > 0 ? String(m).padStart(2, "0") : m}:${String(s).padStart(2, "0")}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 1 })} ${units[unit]}`;
}

export function formatEta(seconds: number | null): string | null {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  if (seconds < 5) return "pochi secondi";
  if (seconds < 60) return `circa ${Math.round(seconds / 5) * 5} s`;
  const minutes = Math.round(seconds / 60);
  return minutes === 1 ? "circa 1 minuto" : `circa ${minutes} minuti`;
}

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  queued: "In coda",
  downloading: "Download",
  separating: "Separazione",
  analyzing: "Analisi",
  aligning: "Allineamento",
  ready: "Completato",
  failed: "Errore",
  cancelled: "Annullato",
};

export const SONG_STATUS_LABEL: Record<SongStatus, string> = {
  importing: "Importazione",
  processing: "Elaborazione",
  ready: "Pronto",
  failed: "Errore",
  cancelled: "Annullato",
};

/** "m:ss.cc" per gli editor di tempi. */
export function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

/** Interpreta "m:ss.cc", "ss.cc" o vuoto (null). `undefined` se il formato non è valido. */
export function parseTimestamp(text: string): number | null | undefined {
  const value = text.trim().replace(",", ".");
  if (value === "") return null;
  const match = /^(?:(\d+):)?(\d+(?:\.\d+)?)$/.exec(value);
  if (!match) return undefined;
  const minutes = match[1] ? Number(match[1]) : 0;
  const secs = Number(match[2]);
  if (match[1] && secs >= 60) return undefined;
  return Math.round((minutes * 60 + secs) * 1000) / 1000;
}
