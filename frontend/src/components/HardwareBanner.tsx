import { useEffect, useState } from "react";

import { Button } from "@/components/ui";
import { apiGet, type HardwareReport } from "@/lib/api";

const DISMISS_KEY = "localchords.hardwareBanner.dismissed";

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(DISMISS_KEY);
  } catch {
    return null;
  }
}

/** Avviso all'avvio: con una GPU NVIDIA l'elaborazione è molto più veloce. */
export function HardwareBanner({ onOpenSettings }: { onOpenSettings: () => void }) {
  const [report, setReport] = useState<HardwareReport | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);

  useEffect(() => {
    const controller = new AbortController();
    apiGet<HardwareReport>("/system/hardware", controller.signal)
      .then(setReport)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  if (!report) return null;
  const gpu = report.info.gpus[0];
  const cudaReady = report.info.runtime.torch_cuda;
  // Il messaggio cambia con l'hardware: chiuderlo vale solo per la situazione attuale.
  const signature = `${gpu?.name ?? "cpu"}|${cudaReady}|${report.separation_runtime}`;
  if (dismissed === signature) return null;

  let tone = "border-line bg-raised";
  let text: string;
  if (!report.separation_runtime) {
    tone = "border-warn/40 bg-warn/10";
    text =
      "Il runtime per la separazione in stem non è installato: riesegui setup.ps1. Analisi e accordi funzionano comunque.";
  } else if (gpu && cudaReady) {
    text = `GPU NVIDIA rilevata (${gpu.name}${gpu.vram_mb ? `, ${Math.round(gpu.vram_mb / 1024)} GB` : ""}): l'elaborazione richiede da pochi secondi a circa un minuto per brano.`;
  } else if (gpu) {
    tone = "border-warn/40 bg-warn/10";
    text = `GPU NVIDIA rilevata (${gpu.name}) ma PyTorch con CUDA non è installato: riesegui setup.ps1 -Runtime nvidia per usarla. Ora l'elaborazione avviene sulla CPU (5-20 minuti per brano).`;
  } else {
    text =
      "Nessuna GPU NVIDIA rilevata: la separazione in stem avviene sulla CPU ed è più lenta (5-20 minuti per brano). Con una GPU NVIDIA bastano secondi o circa un minuto.";
  }

  return (
    <div role="status" className={`flex flex-wrap items-center gap-3 border-b px-5 py-2 text-sm ${tone}`}>
      <p className="min-w-0 flex-1 text-ink-muted">{text}</p>
      <Button variant="ghost" onClick={onOpenSettings}>
        Impostazioni
      </Button>
      <Button
        variant="ghost"
        aria-label="Chiudi l'avviso"
        onClick={() => {
          try {
            window.localStorage.setItem(DISMISS_KEY, signature);
          } catch {
            /* storage non disponibile */
          }
          setDismissed(signature);
        }}
      >
        ✕
      </Button>
    </div>
  );
}
