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

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>)["code"] === "string" &&
    typeof (value as Record<string, unknown>)["message"] === "string"
  );
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, signal ? { signal } : {});
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, {
      code: "network_error",
      message: "Il server locale non risponde",
      detail: null,
    });
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(
      res.status,
      isErrorBody(body)
        ? body
        : { code: "http_error", message: `Errore HTTP ${res.status}`, detail: null },
    );
  }
  return body as T;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: { ok: boolean; revision: string | null; head: string | null };
  worker: { alive: boolean; last_heartbeat: string | null };
  ffmpeg: { available: boolean; path: string | null };
  youtube_enabled: boolean;
  lrclib_enabled: boolean;
}
