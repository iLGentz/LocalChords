# Decisioni tecniche

Registro delle scelte reversibili prese durante lo sviluppo, con il motivo. Le decisioni di
prodotto e di stack approvate sono in `PIANO.md`.

## Test automatici rimandati (24/11/2026)
Su richiesta, la cartella `tests/` (39 test della fase 1 su database, coda, worker e API) è
stata rimossa: i test si scriveranno ed eseguiranno sul PC con la RTX 3080 Ti. Il codice della
fase 1 è stato verificato con quei test prima della rimozione; dalla fase 2 in poi i
controlli sono solo statici (mypy strict, ruff, `tsc`, build) finché non si riprendono.
La configurazione di pytest in `pyproject.toml` resta pronta.

## Fase 4 — separazione, hardware, spazio (24/11/2026)

### audio-separator con PyTorch, non ONNX
Il piano prevede htdemucs_6s in ONNX per il profilo Leggero. Non esiste un export ONNX di
htdemucs verificato (le operazioni STFT/iSTFT sono il punto critico) e il piano stesso chiede
di verificare numericamente ogni conversione prima di renderla predefinita. Scelta:
**audio-separator** (MIT), che esegue sia htdemucs_6s (pesi ufficiali Demucs, PyTorch) sia
BS-RoFormer SW con la stessa interfaccia, con download dei pesi dalle fonti ufficiali. La
conversione in ONNX resta un'ottimizzazione futura, da fare solo dopo il confronto numerico.
Conseguenza: anche il profilo Leggero richiede PyTorch (CPU, ~120 MB di download).

### Runtime come extra esclusivi
`cpu` = torch 2.14 CPU, `nvidia` = torch 2.14 + CUDA 12.6 (indici PyTorch dedicati in
`pyproject.toml`, dichiarati in conflitto tra loro). CUDA 12.6 invece di 13.0 perché
funziona anche con driver NVIDIA meno recenti; la RTX 3080 Ti (Ampere) è supportata da
entrambi. `setup.ps1` rileva la GPU prima di installare le dipendenze e sceglie l'extra.
`audioread` è aggiunto esplicitamente: audio-separator lo usa e librosa 1.0 non lo installa più.

### Processo figlio per la separazione
La separazione gira in `python -m app.separation.runner`: annullare o chiudere l'app termina
subito il processo (le chiamate a torch non sono interrompibili dall'interno), torch non viene
caricato nel worker e un crash per memoria esaurita non abbatte il worker. L'avanzamento viene
dalle barre tqdm su stderr; se non ce ne sono, dal tempo trascorso rispetto alla stima. Per la
sola CPU si imposta `CUDA_VISIBLE_DEVICES=""` nel processo figlio.

### Profili
- **Leggero**: htdemucs_6s su CPU. Sempre disponibile se il runtime è installato.
- **Bilanciato** (DirectML): **non implementato**. `torch-directml` è indietro con le versioni
  di PyTorch e BS-RoFormer non ha un ONNX verificato. Nell'interfaccia il profilo compare
  come non disponibile, con il motivo.
- **Massima qualità**: BS-RoFormer SW su CUDA; richiede GPU NVIDIA con almeno 8 GB e torch
  che veda CUDA (verificato in un sottoprocesso, non con il solo `nvidia-smi`).
- "Automatico" sceglie Massima qualità se disponibile, altrimenti Leggero. Un profilo scelto
  ma non disponibile ricade su Leggero, con una nota.

### Pipeline
import → (separazione automatica, se attiva e il modello è già scaricato) → analisi. Se la
separazione non è possibile l'analisi parte subito sul mix. La separazione manuale accoda poi
una nuova analisi, perché gli accordi usino il mix senza voce e batteria: oggi questo
sostituisce i risultati, quando ci sarà l'editor andrà ristretta agli accordi non modificati.
"Riprova" ripete l'ultimo job fallito (separazione, analisi o import).

### Download dei modelli
Solo su richiesta: dalle impostazioni oppure con "Scarica e separa" nella scheda del brano,
dopo aver mostrato dimensione e licenza. Le dimensioni (53 MB e 668 MB) sono state lette dagli
header HTTP delle fonti il 24/11/2026; quella su disco si misura dopo il download.

### Stime dei tempi
Secondi di calcolo per secondo di audio, per modello e dispositivo, dalle ultime 10 misure
reali; prima della prima misura: htdemucs CPU 1,0, htdemucs CUDA 0,05, RoFormer CUDA 0,15,
RoFormer CPU 6,0. **Valori iniziali da tarare** sul PC di test.

### Spazio su disco
Categorie: audio, stem, waveform, modelli, cache, caricamenti, esportazioni, database. Si
possono svuotare solo le categorie ricostruibili (cache, caricamenti, esportazioni); stem e
modelli si eliminano singolarmente. Il download degli stem come file arriverà con l'export
(fase 9).

## Passaggio a Python 3.12 (24/11/2026, approvato)
Approvato dall'utente dopo la fase 3. numpy 2.5, scipy 1.18 e librosa 1.0 richiedono 3.12 e
i pacchetti dei modelli della fase 4 seguono la stessa strada. `setup.ps1` installa 3.12 in
`.uv\python` e ricrea il venv se l'interprete non corrisponde. `PIANO.md` è aggiornato.

## Fase 3 — analisi (24/11/2026)

### Backend classico (librosa) adesso, modelli neurali con la fase 4
Beat This!, BTC e SongFormer richiedono il download dei pesi "su richiesta, mostrando prima
la dimensione" e la scelta del runtime (ONNX/PyTorch, CPU/GPU): sono parte della gestione dei
modelli della fase 4. In questa fase c'è il backend del profilo Leggero, che funziona su
qualsiasi PC senza scaricare nulla:
- **beat**: `librosa.beat.beat_track`; BPM dalla mediana degli intervalli; confidenza da
  regolarità e forza della pulsazione;
- **downbeat**: in 4/4 si sceglie, tra le 4 fasi, quella con più energia nei bassi (< 200 Hz)
  e più cambi armonici sui beat. Il metro è presunto 4/4 (sarà modificabile nell'editor);
- **accordi**: chroma CQT (36 bin per ottava) della componente armonica (HPSS), mediato per
  beat; 9 qualità (maggiore, minore, 7, maj7, m7, sus4, sus2, dim, aug) per 12 fondamentali,
  bonus se il basso suona la fondamentale, penalità a priori per le qualità complesse;
  Viterbi con probabilità di permanenza 0,82 per beat; rivolto se il basso suona con
  decisione un'altra nota dell'accordo. Accordi salvati con i diesis: la grafia con i bemolle
  e le notazioni si applicano in visualizzazione (fase 7);
- **tonalità**: 0,6 × correlazione con i profili di Krumhansl-Kessler + 0,4 × quota di durata
  degli accordi diatonici; confidenza dal distacco tra prima e seconda candidata;
- **sezioni**: curva di novità di Foote sulla matrice di auto-somiglianza (chroma + MFCC per
  beat), confini distanti almeno 4 battute e agganciati al downbeat, etichette per somiglianza
  armonica, nomi euristici (Intro, Strofa, Ritornello, Bridge, Outro, "Sezione X").

Le costanti (pesi, soglie, probabilità) sono scelte ragionate ma **non tarate su dati**: vanno
verificate su brani reali sul PC di test e, se serve, regolate.

### Pipeline
- Job `analyze` accodato in automatico dalla fase finale dell'import; stato del brano
  `processing` durante l'analisi, `ready` alla fine.
- Fasi con checkpoint: `waveform`, `beats`, `harmony`, `sections`, `save`. I risultati delle
  fasi stanno nel checkpoint (JSON) e solo `save` scrive su DB, sostituendo beat, accordi e
  sezioni in un'unica transazione: un'analisi interrotta non lascia dati a metà.
- Le feature (HPSS, chroma, MFCC, onset) si calcolano una volta e si condividono tra le fasi.
- Gli accordi usano il mix basso + chitarra + piano + altro quando gli stem sono pronti
  (fase 4), altrimenti il mix completo.
- Tempo stimato: secondi di calcolo per secondo di audio per ogni fase, media delle ultime 10
  misure reali (`timing_samples`); prima della prima misura si usano valori prudenti.
- L'annullamento ha effetto tra una fase e l'altra: le chiamate di libreria non sono
  interrompibili.
- "Riprova" su un brano fallito rilancia l'analisi se l'audio normalizzato esiste già,
  altrimenti l'importazione.

### Waveform
Picchi (50 al secondo, 0..1) calcolati a blocchi dal FLAC, in `data/waveforms/<id>/peaks.json`.
Wavesurfer.js li disegna senza decodificare l'audio nel browser, collegato all'elemento
`<audio>`; le sezioni sono regioni colorate non trascinabili (l'editor arriverà dopo).

### Python 3.11 e librerie scientifiche (risolto: passaggio a 3.12, vedi sotto)
Le ultime versioni di numpy (2.5), scipy (1.18) e librosa (1.0) richiedono Python 3.12; con
3.11 uv installa numpy 2.4, scipy 1.17 e librosa 0.11, che vanno bene oggi. Il problema
crescerà con i pacchetti dei modelli (fase 4): **valutare il passaggio a Python 3.12** prima
di quella fase. È un cambio di stack rispetto al piano, quindi va confermato.

## Fase 2 — import (24/11/2026)

### Upload in due passi con anteprima
Il brief chiede l'anteprima dei metadati prima dell'analisi. `POST /api/songs/upload` riceve
il file, lo verifica con ffprobe e restituisce l'anteprima **senza creare il brano**; il file
resta in `data/uploads/<id>/` con un `meta.json`. La conferma (`.../confirm`) crea brano,
asset e job nella stessa transazione. Le anteprime abbandonate si eliminano dopo 24 ore,
all'avvio. Scelta rispetto a "crea subito il brano in bozza": il catalogo non si riempie di
voci mai confermate.

### Corpo grezzo invece di multipart
Il file viaggia come corpo della richiesta (`application/octet-stream`) con il nome
nell'header `X-Filename` (codificato URI). Così il server scrive direttamente su disco
calcolando SHA-256 e dimensione mentre riceve, interrompe appena si supera il limite e non
serve `python-multipart`. Il frontend usa `XMLHttpRequest` per avere l'avanzamento
dell'invio, che `fetch` non espone.

### Validazione in tre livelli
1. estensione (MP3, WAV, M4A, FLAC, OGG) → `unsupported_format` (415) prima di leggere il corpo;
2. ffprobe: contenuto davvero audio e del formato dichiarato, presenza di una traccia audio,
   durata tra 3 s e 60 min → `invalid_audio`, `no_audio_track`, `audio_too_short`,
   `audio_too_long` (422);
3. durante la conversione: picco sotto -60 dBFS → `audio_silent` ("audio senza tracce
   sufficienti").

### Audio normalizzato
Ogni brano ottiene `data/audio/<id>/audio.flac`: FLAC 44,1 kHz, stereo, 16 bit. È il
formato d'ingresso comune per analisi e separazione (BS-RoFormer e htdemucs lavorano a
44,1 kHz) e il player lo riproduce in WebView2. L'originale resta accanto
(`original.<ext>`). Il picco si misura nello stesso passaggio di ffmpeg (`volumedetect`),
senza una seconda decodifica. ffmpeg scrive su un file `.part` rinominato alla fine, e
viene terminato subito in caso di annullamento.

### Cache e duplicati
- File: SHA-256 dell'originale, già calcolato durante l'upload. Se esiste un brano con lo
  stesso checksum, l'anteprima lo segnala e la conferma risponde `duplicate_song` (409) con
  l'id del brano esistente.
- YouTube: prima per URL canonico (`watch?v=<id>`), poi per checksum dopo il download.

### Stato del brano legato al job
Quando un job termina con `failed` o `cancelled` (anche se recuperato dopo un crash del
worker o annullato mentre era in coda), la coda aggiorna nello stesso UPDATE lo stato del
brano collegato. Aggiunto lo stato `cancelled` per i brani; non serve una migrazione perché
gli enum sono stringhe senza vincolo. L'errore mostrato all'utente viene dall'ultimo job.

### Eliminazione di un brano in elaborazione
`DELETE /api/songs/{id}` annulla i job in coda; se uno è in esecuzione chiede l'annullamento
e risponde `song_busy` (409) invece di cancellare file che il worker sta ancora scrivendo.

### YouTube
- yt-dlp come extra opzionale `youtube` con `yt-dlp[default,deno]`: dalla fine del 2025
  yt-dlp richiede un runtime JavaScript esterno per YouTube, e l'extra `deno` lo installa
  come pacchetto Python. L'adapter aggiunge la cartella dell'interprete al `PATH` così che
  yt-dlp lo trovi anche quando l'app parte con `pythonw.exe` senza venv attivo.
  **Da verificare sul PC di test**, insieme al possibile blocco dell'antivirus su `deno.exe`.
- Niente cookie e niente account: nessun aggiramento di limiti d'età, DRM o restrizioni.
- Gli errori di yt-dlp sono tradotti in codici (`video_private`, `video_age_restricted`,
  `video_geo_blocked`, `video_unavailable`, `network_error`, ...). Se un annullamento viene
  trasformato da yt-dlp in un errore generico, il job controlla subito il flag e termina come
  `cancelled`.
- Nessuna miniatura del video: caricarla dall'interfaccia sarebbe una chiamata esterna in
  più.

### Modifica di titolo, artista e album
`PATCH /api/songs/{id}` senza cronologia di annulla/ripristina: il piano la richiede per
accordi, testi, sezioni e grid, che arrivano con l'editor. Se servirà anche per i metadati
si estende `edit_history`.

### Moduli aggiunti all'architettura
`app/importing/` (upload, catalogo, job di import, validazione) e `app/media/` (ffprobe e
ffmpeg), oltre a `app/errors.py` con `AppError`: errore previsto con codice stabile,
tradotto in risposta API con lo stato HTTP giusto (tabella in `app/api/errors.py`) oppure
in errore del job.

## Fase 1 — scheletro (24/11/2026)

### Venv creato con `python -m venv`, non con `uv venv`
Su un PC di sviluppo con Bitdefender Endpoint Security il `python.exe` che uv genera nel venv
(un launcher non firmato) veniva bloccato con "Accesso negato", mentre il launcher standard di
CPython (`Lib\venv\scripts\nt\python.exe`) parte regolarmente. `setup.ps1` quindi:
1. installa Python (ora 3.12) con uv in `.uv\python`;
2. crea `.venv` con `python -m venv --without-pip` usando quell'interprete;
3. lascia a `uv sync` solo l'installazione delle dipendenze (uv riusa il venv esistente).

Per lo stesso motivo **non si usano gli eseguibili degli entry point** in `.venv\Scripts`
(anch'essi launcher di uv): si lancia sempre `python -m ...` (`python -m pytest`,
`python -m app`, `python -m app.worker`). Se il venv esistente non si avvia, `setup.ps1` lo
ricrea.

### SQLite: `BEGIN IMMEDIATE` per le scritture
API e worker sono processi diversi sullo stesso file in modalità WAL. Una transazione `BEGIN`
(deferred) che prima legge e poi scrive fallisce subito con "database is locked" se un altro
processo ha scritto nel frattempo: `busy_timeout` non interviene in quel caso. Il test di
concorrenza l'ha riprodotto. Soluzione: `Database.session()` apre con `BEGIN IMMEDIATE` (prende
subito il lock di scrittura e, se occupato, attende fino a `busy_timeout`);
`Database.read_session()` resta deferred per le letture, che così non bloccano nessuno.

### Coda dei job
- Il claim è un `UPDATE ... WHERE id = ? AND status = 'queued'` (compare-and-set): due worker
  non possono prendere lo stesso job.
- Lo stato iniziale del job dipende dal tipo (es. `separating`, `analyzing`): ogni gestore lo
  dichiara alla registrazione. Non esiste uno stato generico `running`, per restare aderenti
  agli stati del brief.
- Checkpoint per fase in `jobs.checkpoint` (`{"completed": [...], "data": {...}}`): le fasi
  già completate non si rieseguono.
- Chiusura ordinata (stdin chiuso dalla finestra, Ctrl+C): il job torna in coda senza
  consumare un tentativo. Crash del worker: rilevato tramite heartbeat scaduto **o** PID non
  più esistente sullo stesso PC; il job torna in coda e consuma un tentativo (massimo 3, poi
  `failed` con codice `worker_crashed`).
- Annullamento cooperativo: il gestore chiama `ctx.check()` nei cicli lunghi. Le fasi pesanti
  che non possono controllare il flag (es. inferenza in una sola chiamata) andranno eseguite
  in un sottoprocesso terminabile; da decidere nella fase 4.

### Desktop
- API in un thread (uvicorn) e worker in un processo separato, avviati da `app/desktop.py`.
  Il worker osserva il proprio stdin: se la finestra si chiude o va in crash, la pipe si
  chiude e il worker si ferma da solo, senza restare orfano.
- Istanza singola tramite lock su `data/instance.lock`: un secondo avvio apre solo un'altra
  finestra sull'istanza già attiva, senza avviare un secondo worker.
- Porta preferita 8765; se occupata se ne sceglie una libera.
- `pywebview` con `private_mode=False` e `storage_path=data/webview`, così che lo storage del
  browser (preferenze locali dell'interfaccia) sopravviva ai riavvii.
- `python -m app --smoke-test` apre la finestra, verifica che React si sia montato
  (`[data-app-ready]`) e chiude: usato come test automatico della shell desktop.

### Modello dati
- Entità modificabili con colonne `original_*` più correnti, `origin` (`analysis`/`user`) ed
  eliminazione logica (`is_deleted`), così "Ripristina originale" funziona anche su elementi
  cancellati o divisi.
- `edit_history` con `before`/`after` JSON, `group_id` per le operazioni composte (es.
  dividere un accordo) e `undone` per lo stack di ripristino.
- Enum salvati come stringhe senza vincolo CHECK: aggiungere un valore non richiede migrazioni.
- Datetime sempre in UTC con fuso orario (tipo `UTCDateTime`); un datetime senza fuso viene
  rifiutato.
- Le migrazioni non importano tipi dell'app: `env.py` li traduce in tipi SQLAlchemy standard.
  Le migrazioni girano con `foreign_keys=OFF` perché in modalità batch SQLite ricrea le tabelle.

### FFmpeg
Copia portabile da gyan.dev ("release essentials") in `tools\ffmpeg`, scaricata da
`setup.ps1` con verifica SHA-256. Ordine di ricerca: `LOCALCHORDS_FFMPEG_PATH`, poi
`tools\ffmpeg\bin`, poi il PATH. Scelta perché il piano chiede tutto dentro la cartella
dell'app e senza installazioni di sistema.

### Frontend
- Font di sistema (Segoe UI Variable, Cascadia Mono): nessun font scaricato da CDN, l'app deve
  funzionare offline.
- Alias `@/` già configurato per l'aggiunta di shadcn/ui nella fase 8.
- `httpx2` al posto di `httpx` per il `TestClient`: Starlette 1.x segnala `httpx` come
  deprecato.
