import { useCallback, useEffect, useState } from "react";

import { CatalogSidebar } from "@/components/CatalogSidebar";
import { HardwareBanner } from "@/components/HardwareBanner";
import { ImportPanel } from "@/components/ImportPanel";
import { SettingsView } from "@/components/SettingsView";
import { SongView } from "@/components/SongView";
import { StatusBadge } from "@/components/StatusBadge";
import { Button, Notice } from "@/components/ui";
import { useTheme, type ThemeChoice } from "@/hooks/useTheme";
import { useHealth, type HealthState } from "@/hooks/useHealth";
import { useSongs } from "@/hooks/useSongs";
import type { Song } from "@/lib/api";

type View = { kind: "import" } | { kind: "settings" } | { kind: "song"; id: string };

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
        tone={health.ffmpeg.available ? "ok" : "bad"}
        title={health.ffmpeg.path ?? "Esegui setup.ps1 per scaricare FFmpeg"}
      />
    </>
  );
}

const THEME_LABEL: Record<ThemeChoice, string> = { dark: "Scuro", light: "Chiaro", system: "Sistema" };

function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  return (
    <label className="flex items-center gap-1.5 text-xs text-ink-muted">
      Tema
      <select
        value={choice}
        onChange={(e) => setChoice(e.target.value as ThemeChoice)}
        className="rounded-md border border-line bg-ground px-1.5 py-1 text-ink"
      >
        {(Object.keys(THEME_LABEL) as ThemeChoice[]).map((c) => (
          <option key={c} value={c}>
            {THEME_LABEL[c]}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Impedisce a WebView2 di aprire il file rilasciato fuori dalla zona di rilascio. */
function useWindowFileDrop(onFile: (file: File) => void): void {
  useEffect(() => {
    const over = (e: DragEvent): void => e.preventDefault();
    const drop = (e: DragEvent): void => {
      e.preventDefault();
      const file = e.dataTransfer?.files[0];
      if (file) onFile(file);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [onFile]);
}

export function App() {
  const health = useHealth();
  const [query, setQuery] = useState("");
  const { songs, loading, error, refresh } = useSongs(query);
  const [view, setView] = useState<View>({ kind: "import" });
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  // Brano appena creato: lo mostriamo subito, prima che il catalogo si aggiorni.
  const [justCreated, setJustCreated] = useState<Song | null>(null);

  const onWindowDrop = useCallback((file: File) => {
    setView({ kind: "import" });
    setDroppedFile(file);
  }, []);
  useWindowFileDrop(onWindowDrop);

  const version = health.kind === "ok" ? health.health.version : null;
  const youtubeEnabled = health.kind === "ok" && health.health.youtube_enabled;
  const ffmpegMissing = health.kind === "ok" && !health.health.ffmpeg.available;
  const selected =
    view.kind === "song"
      ? (songs.find((s) => s.id === view.id) ??
        (justCreated?.id === view.id ? justCreated : undefined))
      : undefined;

  return (
    <div data-app-ready className="flex h-full min-w-[1280px] flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-brand px-3 py-2 text-on-brand focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Vai al contenuto
      </a>
      <header className="flex items-center gap-4 border-b border-line bg-surface px-5 py-2.5">
        <div className="flex w-72 shrink-0 items-baseline gap-3">
          <span className="font-mono text-lg font-semibold tracking-tight">
            Local<span className="text-brand">Chords</span>
          </span>
          {version && <span className="text-xs text-ink-muted">v{version}</span>}
        </div>
        <div role="search" className="min-w-0 max-w-md flex-1">
          <label htmlFor="catalog-search" className="sr-only">
            Cerca nel catalogo
          </label>
          <input
            id="catalog-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cerca titolo, artista, album"
            className="w-full rounded-md border border-line bg-ground px-3 py-1.5 text-sm placeholder:text-ink-muted focus:border-brand focus:outline-none"
          />
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-2" aria-label="Stato del sistema">
            <SystemStatus state={health} />
          </div>
          <ThemeToggle />
          <Button
            variant={view.kind === "settings" ? "secondary" : "ghost"}
            aria-current={view.kind === "settings" ? "page" : undefined}
            onClick={() => setView({ kind: "settings" })}
          >
            Impostazioni
          </Button>
        </div>
      </header>
      <HardwareBanner onOpenSettings={() => setView({ kind: "settings" })} />

      <div className="flex min-h-0 flex-1">
        <CatalogSidebar
          songs={songs}
          loading={loading}
          error={error}
          query={query}
          selectedId={view.kind === "song" ? view.id : null}
          onSelect={(id) => setView({ kind: "song", id })}
          onImport={() => setView({ kind: "import" })}
          importActive={view.kind === "import"}
        />

        <main id="main" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto px-8 pt-6 focus:outline-none">
          {ffmpegMissing && (
            <div className="mx-auto mb-5 max-w-2xl">
              <Notice tone="error" title="FFmpeg non trovato">
                Senza FFmpeg non è possibile importare audio. Esegui setup.ps1 oppure indica il
                percorso in LOCALCHORDS_FFMPEG_PATH.
              </Notice>
            </div>
          )}

          {view.kind === "import" && (
            <ImportPanel
              youtubeEnabled={youtubeEnabled}
              droppedFile={droppedFile}
              onDroppedFileTaken={() => setDroppedFile(null)}
              onOpenSong={(id) => {
                refresh();
                setView({ kind: "song", id });
              }}
              onStarted={({ song, job }) => {
                setJustCreated({ ...song, job });
                refresh();
                setView({ kind: "song", id: song.id });
              }}
            />
          )}

          {view.kind === "settings" && <SettingsView onStorageChanged={refresh} />}

          {view.kind === "song" && selected && (
            <SongView
              key={selected.id}
              song={selected}
              onChanged={refresh}
              onDeleted={() => {
                refresh();
                setView({ kind: "import" });
              }}
            />
          )}

          {view.kind === "song" && !selected && (
            <p className="text-sm text-ink-muted" aria-live="polite">
              {loading ? "Caricamento…" : "Brano non trovato nel catalogo (forse escluso dalla ricerca)."}
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
