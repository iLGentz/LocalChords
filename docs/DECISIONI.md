# Decisioni tecniche

Registro delle scelte reversibili prese durante lo sviluppo, con il motivo. Le decisioni di
prodotto e di stack approvate sono in `PIANO.md`.

## Test automatici rimandati (24/11/2026)
Su richiesta, la cartella `tests/` (39 test della fase 1 su database, coda, worker e API) è
stata rimossa: i test si scriveranno ed eseguiranno sul PC con la RTX 3080 Ti. Il codice della
fase 1 è stato verificato con quei test prima della rimozione; dalla fase 2 in poi i
controlli sono solo statici (mypy strict, ruff, `tsc`, build) finché non si riprendono.
La configurazione di pytest in `pyproject.toml` resta pronta.

## Fase 1 — scheletro (24/11/2026)

### Venv creato con `python -m venv`, non con `uv venv`
Su un PC di sviluppo con Bitdefender Endpoint Security il `python.exe` che uv genera nel venv
(un launcher non firmato) veniva bloccato con "Accesso negato", mentre il launcher standard di
CPython (`Lib\venv\scripts\nt\python.exe`) parte regolarmente. `setup.ps1` quindi:
1. installa Python 3.11 con uv in `.uv\python`;
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
