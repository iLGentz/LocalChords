import { useState, type FormEvent } from "react";

import { SongWorkspace } from "@/components/SongWorkspace";
import { Button, Notice, ProgressBar, TextField } from "@/components/ui";
import { api, asApiError, isJobActive, type ApiError, type Job, type Song } from "@/lib/api";
import { formatDuration, formatEta, JOB_STATUS_LABEL, SONG_STATUS_LABEL } from "@/lib/format";

interface SongViewProps {
  song: Song;
  onChanged: () => void;
  onDeleted: () => void;
}

export function SongView({ song, onChanged, onDeleted }: SongViewProps) {
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const job = song.job;
  // Il job dei testi ha il suo pannello: qui l'avanzamento degli altri job.
  const active = isJobActive(job) && job?.kind !== "lyrics";

  const run = async (action: () => Promise<unknown>, after: () => void): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      after();
    } catch (err) {
      setError(asApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const cancelJob = (j: Job): void =>
    void run(() => api("POST", `/jobs/${j.id}/cancel`), onChanged);
  const retry = (): void => void run(() => api("POST", `/songs/${song.id}/retry`), onChanged);
  const remove = (): void =>
    void run(() => api("DELETE", `/songs/${song.id}`), () => {
      setConfirmDelete(false);
      onDeleted();
    });

  return (
    <article className="flex w-full flex-col gap-5" aria-labelledby="song-title">
      {editing ? (
        <MetadataForm
          song={song}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
        />
      ) : (
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 id="song-title" className="truncate text-2xl font-semibold">
              {song.title}
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              {[song.artist, song.album].filter(Boolean).join(" · ") || "Artista sconosciuto"}
            </p>
            <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
              <span>Durata {formatDuration(song.duration_s)}</span>
              <span>Origine: {song.source_type === "youtube" ? "YouTube" : "file locale"}</span>
              <span>Stato: {SONG_STATUS_LABEL[song.status]}</span>
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setEditing(true)}>
              Modifica dati
            </Button>
            {!confirmDelete && (
              <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                Elimina
              </Button>
            )}
          </div>
        </header>
      )}

      {confirmDelete && (
        <Notice
          tone="warn"
          title="Eliminare il brano?"
          action={
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={busy}>
                Annulla
              </Button>
              <Button variant="danger" onClick={remove} disabled={busy}>
                Elimina definitivamente
              </Button>
            </div>
          }
        >
          Verranno rimossi l'audio importato e tutti i dati ricavati. L'operazione non si può
          annullare.
        </Notice>
      )}

      {error && (
        <Notice tone="error" title="Operazione non riuscita">
          {error.message}
        </Notice>
      )}

      {job && active && <JobProgress job={job} busy={busy} onCancel={() => cancelJob(job)} />}

      {(song.status === "failed" || song.status === "cancelled") && (
        <Notice
          tone={song.status === "failed" ? "error" : "info"}
          title={
            song.status === "failed" ? "Elaborazione non riuscita" : "Elaborazione annullata"
          }
          action={
            <Button variant="secondary" onClick={retry} disabled={busy}>
              Riprova
            </Button>
          }
        >
          {job?.error?.message ?? "Puoi riprovare."}
        </Notice>
      )}

      {song.status === "ready" && (
        <SongWorkspace
          song={song}
          busy={busy}
          onChanged={onChanged}
          onReanalyze={() => void run(() => api("POST", `/songs/${song.id}/analyze`), onChanged)}
        />
      )}
    </article>
  );
}

function JobProgress({ job, busy, onCancel }: { job: Job; busy: boolean; onCancel: () => void }) {
  const eta = formatEta(job.eta_s);
  return (
    <section
      aria-live="polite"
      aria-label="Avanzamento dell'elaborazione"
      className="rounded-lg border border-line bg-surface p-4"
    >
      <div className="mb-2 flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">
          {JOB_STATUS_LABEL[job.status]}
          {job.message ? ` · ${job.message}` : ""}
        </span>
        <span className="shrink-0 font-mono text-xs text-ink-muted">
          {Math.round(job.progress * 100)}%{eta ? ` · ${eta}` : ""}
        </span>
      </div>
      <ProgressBar
        value={job.status === "queued" ? null : job.progress}
        label="Avanzamento dell'elaborazione"
      />
      <div className="mt-3 flex justify-end">
        <Button variant="ghost" onClick={onCancel} disabled={busy || job.cancel_requested}>
          {job.cancel_requested ? "Annullamento in corso…" : "Annulla"}
        </Button>
      </div>
    </section>
  );
}

function MetadataForm({
  song,
  onCancel,
  onSaved,
}: {
  song: Song;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(song.title);
  const [artist, setArtist] = useState(song.artist ?? "");
  const [album, setAlbum] = useState(song.album ?? "");
  const [error, setError] = useState<ApiError | null>(null);

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    try {
      await api("PATCH", `/songs/${song.id}`, {
        title: title.trim(),
        artist: artist.trim() || null,
        album: album.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(asApiError(err));
    }
  };

  return (
    <form
      onSubmit={(e) => void submit(e)}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
      aria-label="Modifica dati del brano"
    >
      {error && <Notice tone="error">{error.message}</Notice>}
      <TextField id="edit-title" label="Titolo" value={title} onChange={setTitle} required />
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField id="edit-artist" label="Artista" value={artist} onChange={setArtist} />
        <TextField id="edit-album" label="Album" value={album} onChange={setAlbum} />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Annulla
        </Button>
        <Button type="submit" variant="primary" disabled={!title.trim()}>
          Salva
        </Button>
      </div>
    </form>
  );
}
