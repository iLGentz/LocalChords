import { ProgressBar } from "@/components/ui";
import { isJobActive, type ApiError, type Song } from "@/lib/api";
import { formatDuration, SONG_STATUS_LABEL } from "@/lib/format";

interface CatalogSidebarProps {
  songs: Song[];
  loading: boolean;
  error: ApiError | null;
  query: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onImport: () => void;
  importActive: boolean;
}

const STATUS_DOT: Record<Song["status"], string> = {
  importing: "bg-brand animate-pulse",
  processing: "bg-brand animate-pulse",
  ready: "bg-ok",
  failed: "bg-bad",
  cancelled: "bg-ink-muted",
};

export function CatalogSidebar(props: CatalogSidebarProps) {
  const { songs, loading, error, query, selectedId, onSelect, onImport, importActive } =
    props;
  const inProgress = songs.filter((s) => isJobActive(s.job));

  return (
    <aside
      aria-label="Catalogo"
      className="flex w-80 shrink-0 flex-col border-r border-line bg-surface"
    >
      <div className="flex flex-col gap-3 border-b border-line p-4">
        <button
          type="button"
          onClick={onImport}
          aria-current={importActive ? "page" : undefined}
          className="rounded-md bg-brand px-3 py-2 text-sm font-semibold text-on-brand hover:brightness-110"
        >
          Importa brano
        </button>
      </div>

      {inProgress.length > 0 && (
        <section aria-label="Coda di elaborazione" className="border-b border-line p-4">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            In elaborazione ({inProgress.length})
          </h2>
          <ul className="flex flex-col gap-2">
            {inProgress.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onSelect(s.id)}
                  className="w-full rounded-md px-2 py-1.5 text-left hover:bg-raised"
                >
                  <span className="block truncate text-sm">{s.title}</span>
                  <span className="mb-1 block truncate text-xs text-ink-muted">
                    {s.job?.status === "queued" ? "In coda" : (s.job?.message ?? "")}
                  </span>
                  <ProgressBar
                    value={s.job?.status === "queued" ? null : (s.job?.progress ?? null)}
                    label={`Avanzamento di ${s.title}`}
                  />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <nav aria-label="Brani" className="min-h-0 flex-1 overflow-y-auto p-2">
        {error && <p className="p-2 text-sm text-bad">{error.message}</p>}
        {!loading && !error && songs.length === 0 && (
          <p className="p-3 text-sm text-ink-muted">
            {query.trim() ? "Nessun brano corrisponde alla ricerca." : "Il catalogo è vuoto."}
          </p>
        )}
        {loading && songs.length === 0 && (
          <ul aria-hidden="true" className="flex flex-col gap-1 p-1">
            {[0, 1, 2].map((i) => (
              <li key={i} className="h-12 animate-pulse rounded-md bg-raised" />
            ))}
          </ul>
        )}
        <ul className="flex flex-col gap-0.5">
          {songs.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={s.id === selectedId ? "page" : undefined}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left ${
                  s.id === selectedId ? "bg-raised" : "hover:bg-raised/60"
                }`}
              >
                <span
                  className={`size-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`}
                  title={SONG_STATUS_LABEL[s.status]}
                  aria-label={SONG_STATUS_LABEL[s.status]}
                  role="img"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{s.title}</span>
                  <span className="block truncate text-xs text-ink-muted">
                    {s.artist ?? "Artista sconosciuto"}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-xs text-ink-muted">
                  {formatDuration(s.duration_s)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      {/* Sezioni del brano aperto (inserite qui dalla scheda del brano). */}
      <div id="sidebar-sections" className="border-t border-line empty:hidden" />
    </aside>
  );
}
