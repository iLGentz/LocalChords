# Graph Report - LocalChords  (2026-11-24)

## Corpus Check
- 129 files · ~69,695 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1524 nodes · 4443 edges · 95 communities (85 shown, 10 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 698 edges (avg confidence: 0.56)
- Token cost: 104,166 input · 0 output

## Community Hubs (Navigation)
- Analisi beat e armonia
- Fasi di analisi e storage
- Pannelli catalogo e import
- Diagrammi e controlli pratica
- Coda job e cronologia
- Tab con Basic Pitch
- API editor testi
- API brani e YouTube
- Export spartiti e stem
- Motore audio del player
- Shell app e impostazioni
- Import e client API
- Allineamento e editor testi
- Pratica e preferenze
- API di sistema e modelli
- API risultati analisi
- Errori API strutturati
- Config TypeScript app
- Health check
- Avvio desktop pywebview
- Gestione modelli e stem
- Catalogo brani
- Job di analisi
- Job di separazione
- Pannello analisi e accordi
- Modello dati SQLAlchemy
- Upload con anteprima
- Adapter YouTube
- Config shadcn
- Brief e criteri
- Config TypeScript node
- Configurazione e FFmpeg
- Rilevamento hardware
- Algoritmo di allineamento
- Mixer e trasporto
- Karaoke ed editor testi UI
- Wrapper FFmpeg
- Dipendenze frontend
- Dipendenze di sviluppo
- Pulizia storage
- Decisioni di stack
- Server API e config
- Export audio
- Sezioni e trasporto UI
- Componenti UI di base
- Avvio del worker
- Client LRCLIB
- Storage dei brani
- Tipi base del DB
- Runner Whisper
- Decisioni frontend e desktop
- Script npm
- Dipendenze FastAPI
- Modelli Whisper
- Ambiente Alembic
- Runner separazione
- Log JSON
- Segnali dei job
- Ciclo del worker
- Decisioni player
- Connessione SQLite
- Sessioni DB
- API e validazione (doc)
- Decisioni testi
- Decisioni audio e FLAC
- Tsconfig radice
- Contesto dei job
- Decisioni teoria e PDF
- Decisioni modelli di analisi
- Modello dati (doc)
- Decisioni upload e cache
- Pacchetto app
- Dipendenza cva
- Dipendenza lucide
- Dipendenza tw-animate
- Tipi React
- Vincolo solo Windows
- Progetto Python

## God Nodes (most connected - your core abstractions)
1. `Database` - 109 edges
2. `Job` - 81 edges
3. `Song` - 80 edges
4. `Settings` - 79 edges
5. `AppError` - 68 edges
6. `JobStatus` - 59 edges
7. `Storage` - 57 edges
8. `JobOut` - 53 edges
9. `JobContext` - 49 edges
10. `JobQueue` - 47 edges

## Surprising Connections (you probably didn't know these)
- `Analisi classica librosa (beat, chroma CQT + HMM, Krumhansl-Kessler, novita di Foote)` --semantically_similar_to--> `BTC vocabolario esteso (riconoscimento accordi)`  [INFERRED] [semantically similar]
  README.md → PIANO.md
- `Audio normalizzato FLAC 44,1 kHz stereo` --semantically_similar_to--> `Stem salvati in FLAC`  [INFERRED] [semantically similar]
  docs/DECISIONI.md → PIANO.md
- `Frontend Vite + React + TypeScript + Tailwind + shadcn/ui` --semantically_similar_to--> `Next.js (frontend del brief, scartato)`  [EXTRACTED] [semantically similar]
  PIANO.md → BRIEF_ORIGINALE.md
- `Coda job persistente su SQLite con worker separato` --semantically_similar_to--> `Redis job queue (brief, scartato)`  [EXTRACTED] [semantically similar]
  PIANO.md → BRIEF_ORIGINALE.md
- `edit_history: annulla/ripristina persistente, valori originali e correnti` --conceptually_related_to--> `Modello dati minimo (Song, AudioAsset, Stem, ChordEvent, LyricLine, LyricWord, TabNote, Section, UserPreference)`  [INFERRED]
  PIANO.md → BRIEF_ORIGINALE.md

## Import Cycles
- 1-file cycle: `frontend/src/components/ui.tsx -> frontend/src/components/ui.tsx`

## Hyperedges (group relationships)
- **Stack del profilo Leggero (CPU, senza GPU)** — piano_hardware_profiles, piano_htdemucs_6s, readme_librosa_analysis, piano_faster_whisper, docs_decisioni_classic_backend_first [INFERRED 0.85]
- **Pipeline job ripristinabile (coda SQLite, checkpoint, sottoprocessi)** — piano_sqlite_job_queue, piano_job_states, docs_decisioni_job_queue_cas, docs_decisioni_analysis_checkpoints, docs_decisioni_separation_subprocess, docs_decisioni_begin_immediate [INFERRED 0.85]
- **Player Web Audio (SoundTouch, metronomo, waveform canvas)** — docs_decisioni_audio_engine, piano_soundtouch_web_audio, docs_decisioni_metronome_scheduler, docs_decisioni_canvas_waveform [EXTRACTED 1.00]

## Communities (95 total, 10 thin omitted)

### Community 0 - "Analisi beat e armonia"
Cohesion: 0.06
Nodes (56): BeatGrid, detect_beats(), _downbeat_phase(), ndarray, Beat grid, primo battito della battuta e BPM con confidenza (backend librosa)., beat_sync(), Features, load_mono() (+48 more)

### Community 1 - "Fasi di analisi e storage"
Cohesion: 0.08
Nodes (44): _phase_beats(), _phase_sections(), Any, AudioAsset, Database, Motore SQLite condiviso da API e worker (processi diversi, stesso file).  - WAL:, forget(), Rimuove la cronologia di entità che vengono rigenerate (es. nuova analisi). (+36 more)

### Community 2 - "Pannelli catalogo e import"
Cohesion: 0.10
Nodes (48): CatalogSidebarProps, STATUS_DOT, ExportPanel(), ImportPanel(), LyricsPanel(), ModelsSection(), ProcessingSection(), StorageSection() (+40 more)

### Community 3 - "Diagrammi e controlli pratica"
Cohesion: 0.07
Nodes (50): BLACK, BLACK_POS, ChordDiagrams(), ChordDiagramsProps, DiagramInstrument, WHITE, PracticeControls(), PracticeControlsProps (+42 more)

### Community 4 - "Coda job e cronologia"
Cohesion: 0.09
Nodes (22): new_id(), utcnow(), Processi worker attivi, con heartbeat per rilevare quelli morti., Worker, Any, Applica ``changes`` all'entità registrando i valori precedenti., _escape_like(), Catalogo dei brani: creazione da upload o da URL, ricerca, eliminazione, nuovo t (+14 more)

### Community 5 - "Tab con Basic Pitch"
Cohesion: 0.09
Nodes (37): BasicPitch, _clear(), ensure_model(), _inferred_onsets(), load_audio(), _model_frames_to_time(), model_path(), NoteEvent (+29 more)

### Community 6 - "API editor testi"
Cohesion: 0.15
Nodes (41): _changes(), create_line(), create_word(), CreatedOut, _edited_line(), _edited_word(), get_lyrics(), HistoryOut (+33 more)

### Community 7 - "API brani e YouTube"
Cohesion: 0.10
Nodes (38): alias, canonical_url(), Valida un link YouTube e lo riduce alla forma canonica ``watch?v=<id>``., Request, reanalyze(), confirm_upload(), delete_song(), discard_upload() (+30 more)

### Community 8 - "Export spartiti e stem"
Cohesion: 0.13
Nodes (30): _attachment(), download_export(), download_stem(), download_stems_zip(), export(), ExportIn, BaseModel, DatabaseDep (+22 more)

### Community 10 - "Shell app e impostazioni"
Cohesion: 0.09
Nodes (26): App(), THEME_LABEL, ThemeToggle(), useWindowFileDrop(), View, HardwareBanner(), readDismissed(), SettingsView() (+18 more)

### Community 11 - "Import e client API"
Cohesion: 0.09
Nodes (26): ImportPanelProps, PreviewFormProps, Stage, UrlForm(), CATEGORY_LABEL, DEVICE_LABEL, ACTIVE_JOB_STATUSES, ApiErrorBody (+18 more)

### Community 12 - "Allineamento e editor testi"
Cohesion: 0.20
Nodes (30): EditGroup, Raccoglie le modifiche di un'operazione utente dentro una sessione., AppError, Any, Exception, tokenize(), _check_times(), delete_line() (+22 more)

### Community 13 - "Pratica e preferenze"
Cohesion: 0.13
Nodes (29): _chord(), ChordUpdateIn, get_display(), put_display(), Any, BaseModel, DatabaseDep, Response (+21 more)

### Community 14 - "API di sistema e modelli"
Cohesion: 0.25
Nodes (29): CleanupIn, CleanupOut, EstimateOut, HardwareOut, ModelOut, BaseModel, SeparateIn, SeparationPlanOut (+21 more)

### Community 15 - "API risultati analisi"
Cohesion: 0.18
Nodes (27): _phase_save(), AnalysisOut, BeatOut, ChordOut, _chords(), get_analysis(), get_chords(), get_waveform() (+19 more)

### Community 16 - "Errori API strutturati"
Cohesion: 0.12
Nodes (25): ApiError, ErrorBody, install_error_handlers(), not_found(), Any, BaseModel, Exception, FastAPI (+17 more)

### Community 17 - "Config TypeScript app"
Cohesion: 0.07
Nodes (28): compilerOptions, exactOptionalPropertyTypes, isolatedModules, jsx, lib, module, moduleDetection, moduleResolution (+20 more)

### Community 18 - "Health check"
Cohesion: 0.21
Nodes (22): health(), DatabaseDep, QueueDep, SettingsDep, _blank_to_none(), DatabaseHealth, FfmpegHealth, HealthOut (+14 more)

### Community 19 - "Avvio desktop pywebview"
Cohesion: 0.12
Nodes (18): ApiThread, _ensure_std_streams(), InstanceLock, main(), open_window(), pick_port(), Path, Avvio dell'app desktop: migrazioni, API in un thread, worker in un processo sepa (+10 more)

### Community 20 - "Gestione modelli e stem"
Cohesion: 0.15
Nodes (26): delete_model(), delete_stems(), _download_jobs(), download_model(), get_processing(), hardware(), list_stems(), put_processing() (+18 more)

### Community 21 - "Catalogo brani"
Cohesion: 0.19
Nodes (12): Song, _duplicate(), Job, Song, Rimette in coda un brano fallito o annullato: l'analisi se l'audio è già, Rilancia l'analisi (sostituisce i risultati precedenti)., Accoda la separazione in stem (poi la nuova analisi)., Elimina gli stem (file e righe). Restituisce i byte liberati. (+4 more)

### Community 22 - "Job di analisi"
Cohesion: 0.12
Nodes (22): _before(), _enqueue_lyrics(), _Lazy, _measured_ratios(), _phase_waveform(), Path, SongStatus, Job ``analyze``: waveform, beat e BPM, accordi e tonalità, sezioni; poi salvatag (+14 more)

### Community 23 - "Job di separazione"
Cohesion: 0.20
Nodes (24): Device, StrEnum, _download(), _mix(), _plan_dict(), Any, Path, SongStatus (+16 more)

### Community 24 - "Pannello analisi e accordi"
Cohesion: 0.14
Nodes (21): LoopState, snapToBeat(), AnalysisPanel(), AnalysisPanelProps, confidenceLabel(), Fact(), Bar, buildBars() (+13 more)

### Community 25 - "Modello dati SQLAlchemy"
Cohesion: 0.17
Nodes (22): Base, Datetime sempre in UTC e sempre con fuso orario (SQLite non li conserva)., UTCDateTime, AssetKind, EditableMixin, EditAction, EditHistory, LyricsSource (+14 more)

### Community 26 - "Upload con anteprima"
Cohesion: 0.17
Nodes (15): PendingUpload, BaseModel, Upload in due passi: ricezione con anteprima dei metadati, poi conferma.  Il fil, UploadService, check_extension(), check_probe(), _clean(), guess_metadata() (+7 more)

### Community 27 - "Adapter YouTube"
Cohesion: 0.16
Nodes (12): _invalid(), _map_error(), _opt_float(), _opt_str(), Any, Path, ProgressFn, _QuietLogger (+4 more)

### Community 28 - "Config shadcn"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 29 - "Brief e criteri"
Cohesion: 0.11
Nodes (20): BRIEF_ORIGINALE.md (brief originale LocalChords), Criteri di accettazione (12 punti), Canzone demo royalty-free (brief, scartata), Redis job queue (brief, scartato), Song2Chord (prodotto di riferimento), CLAUDE.md (istruzioni progetto), Regola: non inventare risultati audio, docs/DECISIONI.md (registro decisioni tecniche) (+12 more)

### Community 30 - "Config TypeScript node"
Cohesion: 0.10
Nodes (19): compilerOptions, isolatedModules, lib, module, moduleDetection, moduleResolution, noEmit, noUnusedLocals (+11 more)

### Community 31 - "Configurazione e FFmpeg"
Cohesion: 0.16
Nodes (13): Path, Trova FFmpeg: variabile esplicita, poi copia portabile in `tools/`, poi PATH., ffprobe accanto a ffmpeg, altrimenti dal PATH., Settings, Profile, _auto_separation(), Vero se l'utente vuole la separazione automatica e il modello è già scaricato., load() (+5 more)

### Community 32 - "Rilevamento hardware"
Cohesion: 0.20
Nodes (15): build_profiles(), detect(), detect_gpus(), GpuInfo, HardwareInfo, _probe_in_process(), probe_runtime(), ProfileInfo (+7 more)

### Community 33 - "Algoritmo di allineamento"
Cohesion: 0.21
Nodes (17): _align(), align_lines(), AsrWord, _interpolate(), LineOut, lines_from_transcription(), normalize(), Any (+9 more)

### Community 34 - "Mixer e trasporto"
Cohesion: 0.17
Nodes (12): BeatGrid, PlayerSnapshot, Track, TrackSpec, TrackState, MixerPanel(), MixerPanelProps, TransportBarProps (+4 more)

### Community 35 - "Karaoke ed editor testi UI"
Cohesion: 0.13
Nodes (14): chordsByWord(), Editor(), Karaoke(), Mode, Run, SourceActions(), StatusNote(), TimeInput() (+6 more)

### Community 36 - "Wrapper FFmpeg"
Cohesion: 0.20
Nodes (12): AudioStream, MediaTools, _parse_max_volume(), Any, Path, ProgressFn, Wrapper tipizzati per ffprobe e ffmpeg (processi esterni, senza finestra di cons, Converte la prima traccia audio in FLAC stereo 16 bit e misura il picco. (+4 more)

### Community 37 - "Dipendenze frontend"
Cohesion: 0.12
Nodes (17): clsx, dependencies, clsx, radix-ui, react, react-dom, @soundtouchjs/audio-worklet, tailwind-merge (+9 more)

### Community 38 - "Dipendenze di sviluppo"
Cohesion: 0.12
Nodes (17): devDependencies, shadcn, tailwindcss, @tailwindcss/vite, @types/node, @types/react-dom, typescript, vite (+9 more)

### Community 39 - "Pulizia storage"
Cohesion: 0.18
Nodes (12): Elimina le anteprime di upload abbandonate. Restituisce quante ne ha rimosse., Rimozione tollerante: su Windows un file può restare aperto per qualche istante., remove_tree(), category_sizes(), cleanup(), dir_size(), disk_free(), Path (+4 more)

### Community 40 - "Decisioni di stack"
Cohesion: 0.14
Nodes (16): Docker Compose (stack del brief, scartato), audio-separator con PyTorch, non ONNX, Basic Pitch senza TensorFlow (porting ONNX in app/tabs/basic_pitch.py), Profilo Bilanciato (DirectML) non implementato, Passaggio a Python 3.12, Venv con python -m venv, non uv venv (antivirus), Runtime come extra esclusivi (cpu / nvidia CUDA 12.6), Assegnazione corda/tasto con Viterbi (+8 more)

### Community 41 - "Server API e config"
Cohesion: 0.25
Nodes (11): main(), Server API senza finestra, per lo sviluppo: ``uv run localchords-api [--reload]`, get_settings(), Configurazione dell'app, letta da variabili d'ambiente e dal file `.env`.  Tutte, alembic_config(), head_revision(), main(), Esecuzione programmatica delle migrazioni Alembic (all'avvio e nei test). (+3 more)

### Community 42 - "Export audio"
Cohesion: 0.25
Nodes (12): export_dir(), _gains(), Any, Path, Job ``export_audio``: il mix come lo si sente nel player, in WAV o MP3.  - tracc, register(), run_export_audio(), _sources() (+4 more)

### Community 43 - "Sezioni e trasporto UI"
Cohesion: 0.22
Nodes (11): CatalogSidebar(), SectionsNav(), SectionsNavProps, fmt(), TransportBar(), JobStatus, SectionInfo, SongStatus (+3 more)

### Community 44 - "Componenti UI di base"
Cohesion: 0.21
Nodes (11): Button(), buttonVariants, ButtonProps, FieldProps, NOTICE_TONE, NoticeProps, ProgressBarProps, TextField() (+3 more)

### Community 45 - "Avvio del worker"
Cohesion: 0.22
Nodes (12): current_revision(), apply_cpu_limit(), main(), Event, Avvio del processo worker: ``python -m app.worker``.  Opzioni:   --watch-stdin, Limita i thread delle librerie numeriche (da fare prima di importarle)., L'app applica le migrazioni all'avvio; il worker attende e, se serve, le applica, wait_for_schema() (+4 more)

### Community 46 - "Client LRCLIB"
Cohesion: 0.29
Nodes (12): _reference(), fetch(), _get(), LrcLine, LyricsResult, parse_lrc(), plain_lines(), Any (+4 more)

### Community 47 - "Storage dei brani"
Cohesion: 0.30
Nodes (3): _checked_id(), Path, Storage

### Community 48 - "Tipi base del DB"
Cohesion: 0.24
Nodes (7): datetime, StrEnum, Base dichiarativa e tipi comuni per i modelli SQLAlchemy., Enum salvato come stringa (VARCHAR), senza vincolo CHECK: aggiungere valori non, str_enum(), Dialect, Enum

### Community 49 - "Runner Whisper"
Cohesion: 0.33
Nodes (9): _cmd_download(), _cmd_transcribe(), _cuda_dlls(), main(), _progress(), Any, Namespace, Processo figlio per Whisper: ``python -m app.lyrics.runner download|transcribe`` (+1 more)

### Community 50 - "Decisioni frontend e desktop"
Cohesion: 0.22
Nodes (10): Next.js (frontend del brief, scartato), Avvio desktop (app/desktop.py): API in thread, worker in processo, lock istanza singola, Palette e temi (token --brand, .dark predefinito, WCAG >= 4,5:1), shadcn/ui (preset nova, Radix, Tailwind v4), Font di sistema (Segoe UI Variable, Cascadia Mono), nessun CDN, frontend/index.html (entry Vite, html.dark, #root), /src/main.tsx (modulo di avvio React), Backend FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + SQLite (+2 more)

### Community 51 - "Script npm"
Cohesion: 0.20
Nodes (9): name, private, scripts, build, dev, preview, typecheck, type (+1 more)

### Community 52 - "Dipendenze FastAPI"
Cohesion: 0.36
Nodes (8): get_db(), get_queue(), get_settings_dep(), get_songs(), get_storage(), get_uploads(), Request, Dipendenze FastAPI: configurazione, database e coda presi dallo stato dell'app.

### Community 53 - "Modelli Whisper"
Cohesion: 0.47
Nodes (8): list_models(), Path, Modelli Whisper (faster-whisper, licenza MIT) per profilo, scaricati su richiest, whisper_dir(), whisper_for_profile(), whisper_installed(), whisper_size_on_disk(), WhisperSpec

### Community 54 - "Ambiente Alembic"
Cohesion: 0.33
Nodes (8): _database_url(), Any, Ambiente Alembic.  Le migrazioni usano un motore dedicato senza ``foreign_keys=O, Le migrazioni non dipendono dai tipi personalizzati dell'app., _render_item(), run_migrations_offline(), run_migrations_online(), AutogenContext

### Community 55 - "Runner separazione"
Cohesion: 0.47
Nodes (8): _cmd_download(), _cmd_separate(), main(), Any, Namespace, Path, Separazione e download dei modelli in un processo figlio.  Il processo figlio, _separator()

### Community 56 - "Log JSON"
Cohesion: 0.29
Nodes (6): configure_logging(), JsonFormatter, Path, Log strutturati in JSON (una riga per evento) nella cartella `logs/`., Configura il logging del processo: file JSON ruotato più console se disponibile., LogRecord

### Community 57 - "Segnali dei job"
Cohesion: 0.29
Nodes (7): JobCancelled, JobInterrupted, Event, Exception, L'utente ha annullato il job., Il worker si sta chiudendo: il job tornerà in coda dal checkpoint., ClaimedJob

### Community 60 - "Decisioni player"
Cohesion: 0.33
Nodes (6): Motore Web Audio (frontend/src/audio/engine.ts), Waveform su canvas invece di Wavesurfer, Metronomo con scheduler lookahead e count-in, Tipi MIME fissati in app/api/main.py, Web Audio con AudioWorklet SoundTouch, Wavesurfer.js (waveform, plugin regions)

### Community 61 - "Connessione SQLite"
Cohesion: 0.50
Nodes (4): _on_begin(), _on_connect(), Any, Path

### Community 62 - "Sessioni DB"
Cohesion: 0.40
Nodes (3): Session, Sessione di scrittura: commit all'uscita, rollback in caso di errore.          U, Sessione di sola lettura: non blocca gli altri processi.

### Community 63 - "API e validazione (doc)"
Cohesion: 0.40
Nodes (5): API REST minime (/api/songs, /api/jobs, /api/health), AppError (app/errors.py) con codici stabili, Validazione in tre livelli (estensione, ffprobe, picco), Errori API strutturati {code, message, detail}, API disponibili (tabella endpoint)

### Community 64 - "Decisioni testi"
Cohesion: 0.50
Nodes (5): faster-whisper invece di WhisperX, Allineamento testi Needleman-Wunsch con ancore LRCLIB, faster-whisper (trascrizione), LRCLIB (testi sincronizzati, opzionale), WhisperX (allineamento wav2vec2 CTC, pianificato)

### Community 65 - "Decisioni audio e FLAC"
Cohesion: 0.40
Nodes (5): Audio normalizzato FLAC 44,1 kHz stereo, Stem salvati in FLAC, pedalboard (Rubber Band) per export audio, FFmpeg (build gyan.dev essentials, tools\ffmpeg), Licenze GPL (pedalboard, FFmpeg)

### Community 66 - "Tsconfig radice"
Cohesion: 0.40
Nodes (4): compilerOptions, paths, files, references

### Community 68 - "Decisioni teoria e PDF"
Cohesion: 0.50
Nodes (4): Capo suggerito (difficolta pesata per durata), Una sola teoria musicale (frontend/src/lib/music.ts), reportlab (PDF), Tonal.js + chords-db (teoria musicale e diteggiature)

### Community 69 - "Decisioni modelli di analisi"
Cohesion: 0.83
Nodes (4): Backend classico librosa prima dei modelli neurali, Beat This! (CPJKU, beat/downbeat), BTC vocabolario esteso (riconoscimento accordi), Analisi classica librosa (beat, chroma CQT + HMM, Krumhansl-Kessler, novita di Foote)

### Community 72 - "Modello dati (doc)"
Cohesion: 0.67
Nodes (3): Modello dati minimo (Song, AudioAsset, Stem, ChordEvent, LyricLine, LyricWord, TabNote, Section, UserPreference), Colonne original_* + origin + is_deleted, edit_history: annulla/ripristina persistente, valori originali e correnti

### Community 73 - "Decisioni upload e cache"
Cohesion: 0.67
Nodes (3): Corpo grezzo invece di multipart (header X-Filename), Upload in due passi con anteprima, Cache per checksum SHA-256

## Knowledge Gaps
- **176 isolated node(s):** `$schema`, `style`, `rsc`, `tsx`, `config` (+171 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppError` connect `Allineamento e editor testi` to `Fasi di analisi e storage`, `Coda job e cronologia`, `Tab con Basic Pitch`, `API editor testi`, `API brani e YouTube`, `Export spartiti e stem`, `Pratica e preferenze`, `API di sistema e modelli`, `API risultati analisi`, `Errori API strutturati`, `Gestione modelli e stem`, `Catalogo brani`, `Job di separazione`, `Modello dati SQLAlchemy`, `Upload con anteprima`, `Adapter YouTube`, `Configurazione e FFmpeg`, `Wrapper FFmpeg`, `Runner separazione`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `Database` connect `Fasi di analisi e storage` to `Analisi beat e armonia`, `Coda job e cronologia`, `Tab con Basic Pitch`, `API editor testi`, `Export spartiti e stem`, `Allineamento e editor testi`, `Pratica e preferenze`, `API di sistema e modelli`, `API risultati analisi`, `Errori API strutturati`, `Gestione modelli e stem`, `Catalogo brani`, `Job di analisi`, `Job di separazione`, `Modello dati SQLAlchemy`, `Configurazione e FFmpeg`, `Export audio`, `Avvio del worker`, `Storage dei brani`, `Dipendenze FastAPI`, `Segnali dei job`, `Ciclo del worker`, `Connessione SQLite`, `Sessioni DB`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `Settings` connect `Configurazione e FFmpeg` to `Fasi di analisi e storage`, `Wrapper FFmpeg`, `Tab con Basic Pitch`, `Server API e config`, `Export audio`, `Ciclo del worker`, `Pratica e preferenze`, `Client LRCLIB`, `API di sistema e modelli`, `Errori API strutturati`, `Avvio del worker`, `Avvio desktop pywebview`, `Dipendenze FastAPI`, `Job di analisi`, `Job di separazione`, `Upload con anteprima`, `Adapter YouTube`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `Database` (e.g. with `_Lazy` and `EditGroup`) actually correct?**
  _`Database` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 66 inferred relationships involving `Job` (e.g. with `_Lazy` and `export()`) actually correct?**
  _`Job` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 64 inferred relationships involving `Song` (e.g. with `_Lazy` and `_phase_save()`) actually correct?**
  _`Song` has 64 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `Settings` (e.g. with `_QuietLogger` and `VideoInfo`) actually correct?**
  _`Settings` has 20 INFERRED edges - model-reasoned connections that need verification._