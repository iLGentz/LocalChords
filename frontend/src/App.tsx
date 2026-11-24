import { StatusBadge } from "@/components/StatusBadge";
import { useHealth, type HealthState } from "@/hooks/useHealth";

function SystemStatus({ state }: { state: HealthState }) {
  if (state.kind === "loading") {
    return <StatusBadge label="Sistema" value="verifica…" tone="idle" />;
  }
  if (state.kind === "error") {
    return (
      <StatusBadge label="Server" value="non raggiungibile" tone="bad" title={state.error.message} />
    );
  }
  const { health } = state;
  return (
    <>
      <StatusBadge
        label="Database"
        value={health.database.ok ? "pronto" : "da aggiornare"}
        tone={health.database.ok ? "ok" : "bad"}
      />
      <StatusBadge
        label="Elaborazione"
        value={health.worker.alive ? "attiva" : "ferma"}
        tone={health.worker.alive ? "ok" : "warn"}
        title={
          health.worker.alive
            ? "Il worker che elabora i brani è in esecuzione"
            : "Il worker non risponde: controlla logs/worker.log"
        }
      />
      <StatusBadge
        label="FFmpeg"
        value={health.ffmpeg.available ? "trovato" : "mancante"}
        tone={health.ffmpeg.available ? "ok" : "warn"}
        title={health.ffmpeg.path ?? "Esegui setup.ps1 per scaricare FFmpeg"}
      />
    </>
  );
}

export function App() {
  const health = useHealth();
  const version = health.kind === "ok" ? health.health.version : null;

  return (
    <div data-app-ready className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-5 py-3">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-lg font-semibold tracking-tight">
            Local<span className="text-accent">Chords</span>
          </span>
          {version && <span className="text-xs text-ink-muted">v{version}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-live="polite" aria-label="Stato del sistema">
          <SystemStatus state={health} />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center p-8">
        <section className="max-w-md text-center" aria-labelledby="empty-title">
          <h1 id="empty-title" className="text-xl font-semibold">
            Il catalogo è vuoto
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            LocalChords è installato e funzionante. L'importazione dei file audio sarà
            disponibile nella prossima versione.
          </p>
        </section>
      </main>
    </div>
  );
}
