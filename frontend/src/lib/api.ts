/** Client tipizzato per l'API locale. Gli errori arrivano come `{code, message, detail}`. */

export interface ApiErrorBody {
  code: string;
  message: string;
  detail: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
  }
}

const NETWORK_ERROR: ApiErrorBody = {
  code: "network_error",
  message: "Il server locale non risponde",
  detail: null,
};

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>)["code"] === "string" &&
    typeof (value as Record<string, unknown>)["message"] === "string"
  );
}

function toApiError(status: number, body: unknown): ApiError {
  return new ApiError(
    status,
    isErrorBody(body)
      ? body
      : { code: "http_error", message: `Errore HTTP ${status}`, detail: null },
  );
}

export function asApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(0, { code: "unknown", message: String(err), detail: null });
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

export async function api<T>(
  method: Method,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  if (signal) init.signal = signal;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, NETWORK_ERROR);
  }
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, data);
  return data as T;
}

export const apiGet = <T>(path: string, signal?: AbortSignal): Promise<T> =>
  api<T>("GET", path, undefined, signal);

export interface UploadHandle {
  promise: Promise<UploadPreview>;
  abort: () => void;
}

/** Invia il file come corpo grezzo, con avanzamento. */
export function uploadAudio(file: File, onProgress: (fraction: number) => void): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<UploadPreview>((resolve, reject) => {
    xhr.open("POST", "/api/songs/upload");
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* risposta non JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as UploadPreview);
      else reject(toApiError(xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError(0, NETWORK_ERROR));
    xhr.onabort = () =>
      reject(new ApiError(0, { code: "aborted", message: "Caricamento annullato", detail: null }));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

// ---------------------------------------------------------------------- tipi

export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: { ok: boolean; revision: string | null; head: string | null };
  worker: { alive: boolean; last_heartbeat: string | null };
  ffmpeg: { available: boolean; path: string | null };
  youtube_enabled: boolean;
  lrclib_enabled: boolean;
}

export type JobStatus =
  | "queued"
  | "downloading"
  | "separating"
  | "analyzing"
  | "aligning"
  | "ready"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  song_id: string | null;
  kind: string;
  status: JobStatus;
  phase: string | null;
  progress: number;
  message: string | null;
  eta_s: number | null;
  error: { code: string; message: string } | null;
  cancel_requested: boolean;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export type SongStatus = "importing" | "processing" | "ready" | "failed" | "cancelled";

export interface Song {
  id: string;
  title: string;
  artist: string | null;
  album: string | null;
  duration_s: number | null;
  status: SongStatus;
  source_type: "file" | "youtube";
  source_url: string | null;
  key: string | null;
  bpm: number | null;
  created_at: string;
  updated_at: string;
  job: Job | null;
  audio_url: string | null;
}

export interface SongRef {
  id: string;
  title: string;
  artist: string | null;
}

export interface UploadPreview {
  upload_id: string;
  filename: string;
  size_bytes: number;
  format: string;
  codec: string | null;
  duration_s: number | null;
  sample_rate: number | null;
  channels: number | null;
  title: string;
  artist: string | null;
  album: string | null;
  duplicate_of: SongRef | null;
}

export interface UrlPreview {
  url: string;
  title: string;
  artist: string | null;
  album: string | null;
  duration_s: number | null;
  duplicate_of: SongRef | null;
}

export interface SongMetadata {
  title: string;
  artist: string | null;
  album: string | null;
}

export interface ImportStarted {
  song: Song;
  job: Job;
}

export const ACTIVE_JOB_STATUSES: readonly JobStatus[] = [
  "queued",
  "downloading",
  "separating",
  "analyzing",
  "aligning",
];

export function isJobActive(job: Job | null): boolean {
  return job !== null && ACTIVE_JOB_STATUSES.includes(job.status);
}
