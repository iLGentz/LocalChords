import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from "react";

import { Button, Notice, ProgressBar, TextField } from "@/components/ui";
import {
  api,
  asApiError,
  uploadAudio,
  type ApiError,
  type ImportStarted,
  type SongMetadata,
  type SongRef,
  type UploadHandle,
  type UploadPreview,
  type UrlPreview,
} from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";

const ACCEPT = ".mp3,.wav,.m4a,.flac,.ogg";
const FORMATS_LABEL = "MP3, WAV, M4A, FLAC, OGG";

type Stage =
  | { kind: "idle" }
  | { kind: "uploading"; name: string; progress: number }
  | { kind: "probing"; name: string }
  | { kind: "preview-file"; preview: UploadPreview }
  | { kind: "preview-url"; preview: UrlPreview }
  | { kind: "starting" };

interface ImportPanelProps {
  youtubeEnabled: boolean;
  onStarted: (started: ImportStarted) => void;
  onOpenSong: (id: string) => void;
  /** File rilasciato altrove nella finestra. */
  droppedFile: File | null;
  onDroppedFileTaken: () => void;
}

export function ImportPanel(props: ImportPanelProps) {
  const { youtubeEnabled, onStarted, onOpenSong, droppedFile, onDroppedFileTaken } = props;
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [error, setError] = useState<ApiError | null>(null);
  const uploadRef = useRef<UploadHandle | null>(null);

  const startUpload = (file: File): void => {
    setError(null);
    setStage({ kind: "uploading", name: file.name, progress: 0 });
    const handle = uploadAudio(file, (fraction) =>
      setStage(
        fraction >= 1
          ? { kind: "probing", name: file.name }
          : { kind: "uploading", name: file.name, progress: fraction },
      ),
    );
    uploadRef.current = handle;
    handle.promise
      .then((preview) => setStage({ kind: "preview-file", preview }))
      .catch((err: unknown) => {
        const apiErr = asApiError(err);
        if (apiErr.code !== "aborted") setError(apiErr);
        setStage({ kind: "idle" });
      })
      .finally(() => {
        uploadRef.current = null;
      });
  };

  useEffect(() => {
    if (droppedFile && (stage.kind === "idle" || stage.kind === "preview-file")) {
      onDroppedFileTaken();
      startUpload(droppedFile);
    }
  }, [droppedFile]); // reagisce solo a un nuovo file rilasciato

  useEffect(() => () => uploadRef.current?.abort(), []);

  const reset = (): void => {
    if (stage.kind === "preview-file") {
      void api("DELETE", `/songs/upload/${stage.preview.upload_id}`).catch(() => undefined);
    }
    uploadRef.current?.abort();
    setStage({ kind: "idle" });
    setError(null);
  };

  const confirm = async (meta: SongMetadata): Promise<void> => {
    const current = stage;
    setStage({ kind: "starting" });
    setError(null);
    try {
      const started =
        current.kind === "preview-file"
          ? await api<ImportStarted>(
              "POST",
              `/songs/upload/${current.preview.upload_id}/confirm`,
              meta,
            )
          : current.kind === "preview-url"
            ? await api<ImportStarted>("POST", "/songs/import-url", {
                ...meta,
                url: current.preview.url,
              })
            : null;
      if (started) {
        setStage({ kind: "idle" });
        onStarted(started);
      }
    } catch (err) {
      setError(asApiError(err));
      setStage(current);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold">Importa un brano</h1>
        <p className="mt-1 text-sm text-ink-muted">
          L'audio resta sul tuo computer. Formati: {FORMATS_LABEL}.
        </p>
      </div>

      {error && (
        <Notice
          tone="error"
          title="Importazione non riuscita"
          action={<DuplicateAction error={error} onOpenSong={onOpenSong} />}
        >
          {error.message}
        </Notice>
      )}

      {stage.kind === "idle" && (
        <>
          <DropZone onFile={startUpload} />
          {youtubeEnabled && (
            <UrlForm
              onPreview={(preview) => setStage({ kind: "preview-url", preview })}
              onError={setError}
            />
          )}
        </>
      )}

      {(stage.kind === "uploading" || stage.kind === "probing") && (
        <section aria-live="polite" className="rounded-lg border border-line bg-surface p-5">
          <p className="truncate text-sm font-medium">{stage.name}</p>
          <p className="mb-3 mt-1 text-xs text-ink-muted">
            {stage.kind === "uploading"
              ? `Caricamento… ${Math.round(stage.progress * 100)}%`
              : "Verifica del file…"}
          </p>
          <ProgressBar
            value={stage.kind === "uploading" ? stage.progress : null}
            label="Avanzamento del caricamento"
          />
          <div className="mt-4 flex justify-end">
            <Button variant="ghost" onClick={reset}>
              Annulla
            </Button>
          </div>
        </section>
      )}

      {stage.kind === "preview-file" && (
        <PreviewForm
          key={stage.preview.upload_id}
          initial={stage.preview}
          duplicate={stage.preview.duplicate_of}
          facts={[
            ["File", stage.preview.filename],
            ["Formato", `${stage.preview.format}${stage.preview.codec ? ` (${stage.preview.codec})` : ""}`],
            ["Durata", formatDuration(stage.preview.duration_s)],
            ["Dimensione", formatBytes(stage.preview.size_bytes)],
            [
              "Audio",
              [
                stage.preview.sample_rate ? `${(stage.preview.sample_rate / 1000).toLocaleString("it-IT")} kHz` : null,
                stage.preview.channels === 1 ? "mono" : stage.preview.channels === 2 ? "stereo" : stage.preview.channels ? `${stage.preview.channels} canali` : null,
              ]
                .filter(Boolean)
                .join(", ") || "—",
            ],
          ]}
          onConfirm={(meta) => void confirm(meta)}
          onCancel={reset}
          onOpenSong={onOpenSong}
        />
      )}

      {stage.kind === "preview-url" && (
        <PreviewForm
          key={stage.preview.url}
          initial={stage.preview}
          duplicate={stage.preview.duplicate_of}
          facts={[
            ["Link", stage.preview.url],
            ["Durata", formatDuration(stage.preview.duration_s)],
          ]}
          onConfirm={(meta) => void confirm(meta)}
          onCancel={reset}
          onOpenSong={onOpenSong}
        />
      )}

      {stage.kind === "starting" && (
        <section aria-live="polite" className="rounded-lg border border-line bg-surface p-5">
          <p className="mb-3 text-sm">Avvio dell'importazione…</p>
          <ProgressBar value={null} label="Avvio dell'importazione" />
        </section>
      )}
    </div>
  );
}

function DuplicateAction({ error, onOpenSong }: { error: ApiError; onOpenSong: (id: string) => void }) {
  const detail = error.detail as { song_id?: unknown } | null;
  if (error.code !== "duplicate_song" || typeof detail?.song_id !== "string") return null;
  const songId = detail.song_id;
  return (
    <Button variant="secondary" onClick={() => onOpenSong(songId)}>
      Apri il brano
    </Button>
  );
}

function DropZone({ onFile }: { onFile: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const hintId = useId();

  const onDrop = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setOver(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-14 text-center transition-colors ${
        over ? "border-accent bg-accent/5" : "border-line bg-surface"
      }`}
    >
      <p className="text-base font-medium">Trascina qui un file audio</p>
      <p id={hintId} className="text-sm text-ink-muted">
        oppure
      </p>
      <Button variant="primary" aria-describedby={hintId} onClick={() => inputRef.current?.click()}>
        Scegli un file
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onFile(file);
        }}
      />
    </div>
  );
}

function UrlForm({
  onPreview,
  onError,
}: {
  onPreview: (preview: UrlPreview) => void;
  onError: (error: ApiError | null) => void;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    onError(null);
    try {
      onPreview(await api<UrlPreview>("POST", "/songs/import-url/preview", { url: url.trim() }));
    } catch (err) {
      onError(asApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="rounded-lg border border-line bg-surface p-4">
      <label htmlFor="yt-url" className="text-sm font-medium">
        Oppure incolla un link YouTube
      </label>
      <div className="mt-2 flex gap-2">
        <input
          id="yt-url"
          type="url"
          inputMode="url"
          value={url}
          placeholder="https://www.youtube.com/watch?v=…"
          onChange={(e) => setUrl(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-line bg-ground px-2.5 py-1.5 text-sm focus:border-accent focus:outline-none"
        />
        <Button type="submit" variant="secondary" disabled={busy || !url.trim()}>
          {busy ? "Verifica…" : "Anteprima"}
        </Button>
      </div>
    </form>
  );
}

interface PreviewFormProps {
  initial: SongMetadata;
  duplicate: SongRef | null;
  facts: [string, string][];
  onConfirm: (meta: SongMetadata) => void;
  onCancel: () => void;
  onOpenSong: (id: string) => void;
}

function PreviewForm({ initial, duplicate, facts, onConfirm, onCancel, onOpenSong }: PreviewFormProps) {
  const [title, setTitle] = useState(initial.title);
  const [artist, setArtist] = useState(initial.artist ?? "");
  const [album, setAlbum] = useState(initial.album ?? "");

  const submit = (e: FormEvent): void => {
    e.preventDefault();
    if (!title.trim() || duplicate) return;
    onConfirm({ title: title.trim(), artist: artist.trim() || null, album: album.trim() || null });
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5">
      <h2 className="text-base font-semibold">Controlla i dati prima di importare</h2>

      {duplicate && (
        <Notice
          tone="warn"
          title="Brano già presente"
          action={
            <Button variant="secondary" onClick={() => onOpenSong(duplicate.id)}>
              Apri il brano
            </Button>
          }
        >
          Questo audio è già nel catalogo come «{duplicate.title}»
          {duplicate.artist ? ` di ${duplicate.artist}` : ""}: non serve analizzarlo di nuovo.
        </Notice>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <TextField id="meta-title" label="Titolo" value={title} onChange={setTitle} required />
        </div>
        <TextField id="meta-artist" label="Artista" value={artist} onChange={setArtist} />
        <TextField id="meta-album" label="Album" value={album} onChange={setAlbum} />
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md bg-ground px-3 py-2.5 text-xs">
        {facts.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-muted">{k}</dt>
            <dd className="truncate font-mono" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Annulla
        </Button>
        <Button type="submit" variant="primary" disabled={!title.trim() || duplicate !== null}>
          Importa
        </Button>
      </div>
    </form>
  );
}
