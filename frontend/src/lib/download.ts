import { ApiError } from "@/lib/api";

function filenameFrom(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? fallback;
}

/** Salva un file (Download di Windows) avviando il download dal browser. */
function save(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** POST che restituisce un file: lo scarica con il nome indicato dal server. */
export async function postDownload(
  path: string,
  body: unknown,
  fallbackName: string,
): Promise<void> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null);
    const err = data as { code?: string; message?: string } | null;
    throw new ApiError(res.status, {
      code: err?.code ?? "http_error",
      message: err?.message ?? `Errore HTTP ${res.status}`,
      detail: null,
    });
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  save(url, filenameFrom(res.headers.get("content-disposition"), fallbackName));
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** GET di un file servito dal backend (il nome arriva da Content-Disposition). */
export function getDownload(path: string): void {
  save(`/api${path}`, "");
}
