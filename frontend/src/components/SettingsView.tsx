import { useCallback, useEffect, useState } from "react";

import { Button, Notice, ProgressBar } from "@/components/ui";
import {
  api,
  apiGet,
  asApiError,
  isJobActive,
  type ApiError,
  type DeviceChoice,
  type HardwareReport,
  type ModelInfo,
  type ProcessingPreferences,
  type ProfileChoice,
  type StorageReport,
} from "@/lib/api";
import { THEME_LABEL, useTheme, type ThemeChoice } from "@/hooks/useTheme";
import { formatBytes, formatEta } from "@/lib/format";

export function SettingsView({ onStorageChanged }: { onStorageChanged: () => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <h1 className="text-xl font-semibold">Impostazioni</h1>
      <AppearanceSection />
      <ProcessingSection />
      <ModelsSection />
      <StorageSection onChanged={onStorageChanged} />
      <section aria-labelledby="legal-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
        <h2 id="legal-title" className="mb-2 font-semibold">
          Note legali
        </h2>
        <ul className="list-disc space-y-1 pl-5 text-ink-muted">
          <li>Gli stem servono per studio e pratica personale.</li>
          <li>
            I pesi di BS-RoFormer SW sono rilasciati con licenza CC-BY-NC-SA-4.0: solo uso non
            commerciale.
          </li>
          <li>LocalChords non include canzoni né testi protetti e non invia i tuoi file all'esterno.</li>
        </ul>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ aspetto

const THEME_HINT: Record<ThemeChoice, string> = {
  dark: "Scuro \"studio\", toni caldi, accento ambra.",
  light: "Chiaro, per ambienti luminosi.",
  cyber: "Nero e bordeaux, accenti turchese e giallo, pannelli ad angolo tagliato.",
  system: "Segue l'impostazione chiaro/scuro di Windows.",
};

function AppearanceSection() {
  const { choice, setChoice } = useTheme();
  return (
    <section aria-labelledby="appearance-title" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="appearance-title" className="mb-3 font-semibold">
        Aspetto
      </h2>
      <div role="radiogroup" aria-labelledby="appearance-title" className="grid gap-2 sm:grid-cols-2">
        {(Object.keys(THEME_LABEL) as ThemeChoice[]).map((c) => (
          <label
            key={c}
            className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-sm ${
              choice === c ? "border-brand bg-brand/10" : "border-line"
            }`}
          >
            <input
              type="radio"
              name="theme"
              value={c}
              checked={choice === c}
              onChange={() => setChoice(c)}
              className="mt-0.5 accent-[var(--brand)]"
            />
            <span>
              <span className="font-medium">{THEME_LABEL[c]}</span>
              <span className="block text-xs text-ink-muted">{THEME_HINT[c]}</span>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}

// ------------------------------------------------------------- elaborazione

const DEVICE_LABEL: Record<DeviceChoice, string> = {
  auto: "Automatico",
  nvidia: "GPU NVIDIA",
  cpu: "Solo CPU",
};

function ProcessingSection() {
  const [report, setReport] = useState<HardwareReport | null>(null);
  const [prefs, setPrefs] = useState<ProcessingPreferences | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback((refresh: boolean) => {
    apiGet<HardwareReport>(`/system/hardware${refresh ? "?refresh=true" : ""}`)
      .then((r) => {
        setReport(r);
        setPrefs(r.preferences);
      })
      .catch((e: unknown) => setError(asApiError(e)));
  }, []);
  useEffect(() => load(false), [load]);

  const update = async (next: ProcessingPreferences): Promise<void> => {
    setPrefs(next);
    setSaved(false);
    try {
      setPrefs(await api<ProcessingPreferences>("PUT", "/settings/processing", next));
      setSaved(true);
    } catch (e) {
      setError(asApiError(e));
    }
  };

  const info = report?.info;
  return (
    <section aria-labelledby="proc-title" className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id="proc-title" className="font-semibold">
          Elaborazione e hardware
        </h2>
        <Button variant="ghost" onClick={() => load(true)}>
          Rileva di nuovo
        </Button>
      </div>
      {error && <Notice tone="error">{error.message}</Notice>}
      {!info || !prefs ? (
        <div className="h-24 animate-pulse rounded-md bg-raised" aria-hidden="true" />
      ) : (
        <div className="flex flex-col gap-4 text-sm">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-ink-muted">CPU</dt>
            <dd>
              {info.cpu} ({info.cpu_cores} thread){info.ram_gb ? `, ${info.ram_gb} GB di RAM` : ""}
            </dd>
            <dt className="text-ink-muted">GPU NVIDIA</dt>
            <dd>
              {info.gpus.length === 0
                ? "nessuna"
                : info.gpus
                    .map((g) => `${g.name}${g.vram_mb ? ` (${Math.round(g.vram_mb / 1024)} GB)` : ""}`)
                    .join(", ")}
            </dd>
            <dt className="text-ink-muted">PyTorch</dt>
            <dd>
              {info.runtime.torch_version
                ? `${info.runtime.torch_version}${info.runtime.torch_cuda ? " con CUDA" : " (CPU)"}`
                : "non installato"}
            </dd>
          </dl>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-ink-muted">Dispositivo</legend>
            <div className="flex flex-wrap gap-2" role="radiogroup">
              {(Object.keys(DEVICE_LABEL) as DeviceChoice[]).map((d) => (
                <label
                  key={d}
                  className={`cursor-pointer rounded-md border px-3 py-1.5 ${prefs.device === d ? "border-brand bg-brand/10" : "border-line"}`}
                >
                  <input
                    type="radio"
                    name="device"
                    className="sr-only"
                    checked={prefs.device === d}
                    onChange={() => void update({ ...prefs, device: d })}
                  />
                  {DEVICE_LABEL[d]}
                </label>
              ))}
            </div>
            <p className="text-xs text-ink-muted">
              Si può cambiare anche per il singolo brano al momento della separazione.
            </p>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-ink-muted">Profilo</legend>
            <ProfileOption
              id="auto"
              label={`Automatico (consigliato: ${info.profiles.find((p) => p.id === info.recommended)?.label ?? ""})`}
              detail={null}
              available
              checked={prefs.profile === "auto"}
              onSelect={() => void update({ ...prefs, profile: "auto" })}
            />
            {info.profiles.map((p) => {
              const est = report.estimates.find((e) => e.profile === p.id);
              return (
                <ProfileOption
                  key={p.id}
                  id={p.id}
                  label={p.label}
                  detail={
                    p.available
                      ? `${p.separation_model} su ${p.device === "cuda" ? "GPU" : "CPU"}${est ? ` · brano di 4 min: ${formatEta(est.seconds_for_4min) ?? "—"}` : ""}`
                      : p.reason
                  }
                  available={p.available}
                  checked={prefs.profile === p.id}
                  onSelect={() => void update({ ...prefs, profile: p.id })}
                />
              );
            })}
          </fieldset>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={prefs.auto_separate}
              onChange={(e) => void update({ ...prefs, auto_separate: e.target.checked })}
              className="size-4 accent-[var(--brand)]"
            />
            Separa automaticamente in stem dopo l'importazione (se il modello è scaricato)
          </label>
          {saved && (
            <p className="text-xs text-ok" role="status">
              Salvato.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function ProfileOption(props: {
  id: ProfileChoice;
  label: string;
  detail: string | null;
  available: boolean;
  checked: boolean;
  onSelect: () => void;
}) {
  return (
    <label
      className={`flex cursor-pointer flex-col rounded-md border px-3 py-2 ${props.checked ? "border-brand bg-brand/10" : "border-line"} ${props.available ? "" : "cursor-not-allowed opacity-60"}`}
    >
      <span className="flex items-center gap-2">
        <input
          type="radio"
          name="profile"
          checked={props.checked}
          disabled={!props.available}
          onChange={props.onSelect}
          className="accent-[var(--brand)]"
        />
        {props.label}
      </span>
      {props.detail && <span className="pl-6 text-xs text-ink-muted">{props.detail}</span>}
    </label>
  );
}

// ------------------------------------------------------------------ modelli

function ModelsSection() {
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);
  const [confirm, setConfirm] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    apiGet<ModelInfo[]>("/models", controller.signal)
      .then((m) => {
        setModels(m);
        if (m.some((x) => isJobActive(x.download_job))) {
          timer = window.setTimeout(() => setTick((t) => t + 1), 1000);
        }
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(asApiError(e));
      });
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [tick]);

  const act = async (method: "POST" | "DELETE", path: string): Promise<void> => {
    setError(null);
    setConfirm(null);
    try {
      await api(method, path);
    } catch (e) {
      setError(asApiError(e));
    }
    setTick((t) => t + 1);
  };

  return (
    <section aria-labelledby="models-title" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="models-title" className="mb-1 font-semibold">
        Modelli di separazione
      </h2>
      <p className="mb-3 text-xs text-ink-muted">
        Si scaricano solo quando servono. Puoi eliminarli per liberare spazio.
      </p>
      {error && <Notice tone="error">{error.message}</Notice>}
      <ul className="flex flex-col gap-3">
        {models?.map((m) => {
          const job = m.download_job;
          return (
            <li key={m.id} className="rounded-md border border-line p-3 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{m.label}</p>
                  <p className="text-xs text-ink-muted">{m.description}</p>
                  <p className="mt-1 text-xs text-ink-muted">
                    Licenza {m.license}
                    {m.commercial_use ? "" : " (solo uso non commerciale)"} ·{" "}
                    {m.installed ? `installato, ${formatBytes(m.size_on_disk)}` : `circa ${m.size_mb} MB da scaricare`}
                  </p>
                </div>
                {!job &&
                  (m.installed ? (
                    confirm === m.id ? (
                      <div className="flex gap-2">
                        <Button variant="ghost" onClick={() => setConfirm(null)}>
                          Annulla
                        </Button>
                        <Button variant="danger" onClick={() => void act("DELETE", `/models/${m.id}`)}>
                          Elimina
                        </Button>
                      </div>
                    ) : (
                      <Button variant="ghost" onClick={() => setConfirm(m.id)}>
                        Elimina
                      </Button>
                    )
                  ) : (
                    <Button variant="secondary" onClick={() => void act("POST", `/models/${m.id}/download`)}>
                      Scarica ({m.size_mb} MB)
                    </Button>
                  ))}
              </div>
              {job && (
                <div className="mt-2 flex items-center gap-3">
                  <ProgressBar value={job.status === "queued" ? null : job.progress} label={`Download di ${m.label}`} />
                  <Button variant="ghost" onClick={() => void act("POST", `/jobs/${job.id}/cancel`)}>
                    Annulla
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ----------------------------------------------------------- spazio su disco

const CATEGORY_LABEL: Record<string, string> = {
  audio: "Audio importato",
  stems: "Stem",
  waveforms: "Waveform",
  models: "Modelli",
  cache: "Cache",
  uploads: "Caricamenti non confermati",
  exports: "Esportazioni",
  database: "Database",
};

function StorageSection({ onChanged }: { onChanged: () => void }) {
  const [report, setReport] = useState<StorageReport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    apiGet<StorageReport>("/system/storage", controller.signal)
      .then(setReport)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(asApiError(e));
      });
    return () => controller.abort();
  }, [tick]);

  const run = async (method: "POST" | "DELETE", path: string, body?: unknown): Promise<void> => {
    setError(null);
    try {
      const res = await api<{ freed_bytes: number }>(method, path, body);
      setMessage(`Spazio liberato: ${formatBytes(res.freed_bytes)}`);
      onChanged();
    } catch (e) {
      setError(asApiError(e));
    }
    setTick((t) => t + 1);
  };

  return (
    <section aria-labelledby="storage-title" className="rounded-lg border border-line bg-surface p-4 text-sm">
      <h2 id="storage-title" className="mb-1 font-semibold">
        Spazio su disco
      </h2>
      {error && <Notice tone="error">{error.message}</Notice>}
      {message && (
        <p role="status" className="mb-2 text-xs text-ok">
          {message}
        </p>
      )}
      {!report ? (
        <div className="h-24 animate-pulse rounded-md bg-raised" aria-hidden="true" />
      ) : (
        <>
          <p className="mb-3 text-xs text-ink-muted">
            LocalChords occupa {formatBytes(report.total)} in {report.data_dir}. Liberi sul disco:{" "}
            {formatBytes(report.disk_free)}.
          </p>
          <dl className="mb-3 grid grid-cols-[1fr_auto_auto] items-center gap-x-4 gap-y-1">
            {Object.entries(report.categories).map(([key, size]) => (
              <div key={key} className="contents">
                <dt>{CATEGORY_LABEL[key] ?? key}</dt>
                <dd className="text-right font-mono text-xs">{formatBytes(size)}</dd>
                <dd>
                  {report.cleanable.includes(key) && size > 0 ? (
                    <Button variant="ghost" onClick={() => void run("POST", "/system/storage/cleanup", { targets: [key] })}>
                      Svuota
                    </Button>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          {report.songs.some((s) => s.stems > 0) && (
            <>
              <h3 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Stem per brano
              </h3>
              <ul className="flex flex-col gap-1">
                {report.songs
                  .filter((s) => s.stems > 0)
                  .map((s) => (
                    <li key={s.song_id} className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate">
                        {s.title}
                        {s.artist ? ` · ${s.artist}` : ""}
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-xs">{formatBytes(s.stems)}</span>
                        <Button variant="ghost" onClick={() => void run("DELETE", `/songs/${s.song_id}/stems`)}>
                          Elimina stem
                        </Button>
                      </span>
                    </li>
                  ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
