import { useEffect, useState } from "react";

import { Button, Notice } from "@/components/ui";
import {
  api,
  apiGet,
  asApiError,
  type ApiError,
  type DeviceChoice,
  type SeparationPlan,
  type Song,
  type StemInfo,
} from "@/lib/api";
import { formatBytes, formatEta } from "@/lib/format";

export const STEM_LABEL: Record<StemInfo["type"], string> = {
  vocals: "Voce",
  drums: "Batteria",
  bass: "Basso",
  guitar: "Chitarra",
  piano: "Pianoforte",
  other: "Altro",
};

interface StemsPanelProps {
  song: Song;
  stems: StemInfo[] | null;
  onChanged: () => void;
}

/** Separazione in stem (avvio, modello, dispositivo) ed eliminazione. L'ascolto è nel mixer. */
export function StemsPanel({ song, stems, onChanged }: StemsPanelProps) {
  const [error, setError] = useState<ApiError | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const removeStems = async (): Promise<void> => {
    try {
      await api("DELETE", `/songs/${song.id}/stems`);
      setConfirmDelete(false);
      onChanged();
    } catch (e) {
      setError(asApiError(e));
    }
  };

  return (
    <section aria-labelledby="stems-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="stems-title" className="text-base font-semibold">
          Stem
        </h2>
        <p className="text-xs text-ink-muted">Per studio e pratica personale.</p>
      </div>
      {error && <Notice tone="error">{error.message}</Notice>}
      {stems === null && <div className="h-16 animate-pulse rounded-md bg-raised" aria-hidden="true" />}
      {stems !== null && stems.length === 0 && <SeparateForm song={song} onStarted={onChanged} />}
      {stems !== null && stems.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
          <span>
            {stems.length} stem ({stems.map((s) => STEM_LABEL[s.type]).join(", ")}) · modello{" "}
            {stems[0]?.model ?? "—"} · {formatBytes(stems.reduce((sum, s) => sum + (s.size_bytes ?? 0), 0))}.
            Regolali dal mixer.
          </span>
          {confirmDelete ? (
            <span className="flex gap-2">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                Annulla
              </Button>
              <Button variant="danger" onClick={() => void removeStems()}>
                Elimina stem
              </Button>
            </span>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
              Elimina stem
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function SeparateForm({ song, onStarted }: { song: Song; onStarted: () => void }) {
  const [device, setDevice] = useState<DeviceChoice>("auto");
  const [plan, setPlan] = useState<SeparationPlan | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setPlan(null);
    setError(null);
    apiGet<SeparationPlan>(`/songs/${song.id}/separation-plan?device=${device}`, controller.signal)
      .then(setPlan)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(asApiError(e));
      });
    return () => controller.abort();
  }, [song.id, device]);

  const start = async (): Promise<void> => {
    setBusy(true);
    try {
      await api("POST", `/songs/${song.id}/separate`, {
        device,
        allow_download: plan ? !plan.model_installed : false,
      });
      onStarted();
    } catch (e) {
      setError(asApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-muted">
        Separa il brano in 6 stem: voce, batteria, basso, chitarra, pianoforte e altro. Dopo la
        separazione gli accordi vengono ricalcolati senza voce e batteria.
      </p>
      <label className="flex items-center gap-2">
        <span className="text-ink-muted">Dispositivo per questo brano</span>
        <select
          value={device}
          onChange={(e) => setDevice(e.target.value as DeviceChoice)}
          className="rounded-md border border-line bg-ground px-2 py-1"
        >
          <option value="auto">Automatico</option>
          <option value="nvidia">GPU NVIDIA</option>
          <option value="cpu">Solo CPU</option>
        </select>
      </label>
      {error && <Notice tone="error">{error.message}</Notice>}
      {plan && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-ground px-3 py-2">
          <div className="text-xs text-ink-muted">
            <p>
              {plan.model_label} su {plan.device === "cuda" ? "GPU" : "CPU"} · tempo stimato{" "}
              {formatEta(plan.eta_s) ?? "—"}
            </p>
            {!plan.model_installed && (
              <p className="text-warn">
                Prima verrà scaricato il modello (circa {plan.model_size_mb} MB, licenza {plan.model_license}).
              </p>
            )}
            {plan.note && <p>{plan.note}</p>}
          </div>
          <Button variant="primary" disabled={busy} onClick={() => void start()}>
            {plan.model_installed ? "Separa in 6 stem" : `Scarica (${plan.model_size_mb} MB) e separa`}
          </Button>
        </div>
      )}
    </div>
  );
}
