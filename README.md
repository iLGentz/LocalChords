# LocalChords

App desktop **per Windows 10/11 (x64)**, local-first. Gli dai un file audio e ti restituisce:

- **accordi** sincronizzati con la musica, per battuta;
- **testo** sincronizzato parola per parola (karaoke), modificabile;
- **6 stem** separati (voce, batteria, basso, chitarra, pianoforte, altro) con mixer;
- **strumenti di pratica**: velocità, tonalità, loop, metronomo, trasposizione, capo,
  diagrammi e tab;
- **export** in PDF, TXT, ChordPro, MP3/WAV.

Tutto gira sul tuo PC: nessun account, nessun servizio cloud obbligatorio.

> **Stato:** fase 9 di 10. Scheletro, importazione da file locale (e da YouTube, se
> attivato), analisi (beat grid, BPM, tonalità, accordi, sezioni, waveform), separazione in
> 6 stem, rilevamento dell'hardware con profili, gestione dello spazio su disco e testi
> sincronizzati parola per parola con editor, player con mixer degli stem, velocità, tonalità,
> loop e metronomo, trasposizione, capo, semplificazione, notazioni, diagrammi, tab e interfaccia
> completa (temi Scuro, Chiaro e Cyber, 3 colonne) ed export. Resta la verifica end-to-end (fase 10).
>
> Test eseguiti il 24/11/2026 su un PC **senza GPU** (CPU Intel, 16 GB): 58 test pytest
> (anche separazione htdemucs_6s, tab con Basic Pitch e Whisper small, tutti su CPU),
> 13 test Vitest e 6 test end-to-end Playwright su brani sintetici. Restano da verificare sul
> PC con GPU NVIDIA: separazione BS-RoFormer su CUDA, Whisper su GPU, profilo Massima qualità
> e brani reali.
>
> I punti marcati **⚠ Da verificare** non sono ancora stati provati da capo a fondo.

## Prima di iniziare

| Cosa | Perché | Come averlo |
|---|---|---|
| Windows 10 o 11, 64 bit | unico sistema supportato | — |
| [uv](https://docs.astral.sh/uv/) | Python isolato e dipendenze | `setup.ps1` prova a installarlo con winget, oppure `winget install astral-sh.uv` |
| [Node.js](https://nodejs.org/) 20 o superiore | solo per compilare l'interfaccia (non serve in esecuzione) | `winget install OpenJS.NodeJS.LTS` |
| Microsoft Edge WebView2 | mostra la finestra dell'app | già incluso in Windows 11 |
| FFmpeg | decodifica ed export audio | `setup.ps1` scarica una copia portabile in `tools\ffmpeg` |
| Connessione internet | download di Python, librerie, FFmpeg e modelli | solo per l'installazione e i modelli |
| GPU NVIDIA (facoltativa) | elaborazione molto più veloce | senza GPU l'app usa il profilo "Leggero" su CPU: funziona tutto, ma più lentamente |

Python **non** va installato a parte: `setup.ps1` fa scaricare a uv Python 3.12 dentro la
cartella dell'app (`.uv\python`), senza toccare quello di sistema.

## Installazione

1. Apri PowerShell nella cartella del progetto.
2. Avvia lo script di installazione:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```

   Lo script, nell'ordine:
   - controlla il sistema;
   - installa uv e Python 3.12 in `.uv\python`;
   - rileva la GPU e sceglie PyTorch per CPU o per CUDA;
   - crea `.venv` e installa le dipendenze;
   - scarica FFmpeg in `tools\ffmpeg`, verificandone l'integrità;
   - compila l'interfaccia;
   - prepara il database.

3. Attendi il messaggio finale `Installazione completata`. Il primo download di PyTorch
   può richiedere qualche minuto.

Opzioni utili:

| Opzione | Effetto |
|---|---|
| `-Runtime auto\|cpu\|nvidia` | runtime di separazione da installare: PyTorch CPU oppure CUDA 12.6 (predefinito `auto`: NVIDIA se `nvidia-smi` risponde) |
| `-SkipFfmpeg` | non scarica FFmpeg (se lo hai già nel PATH o lo installerai dopo) |
| `-SkipFrontend` | non ricompila l'interfaccia |
| `-Dev` | installa anche gli strumenti di sviluppo (pytest, mypy, ruff) |
| `-YouTube` | installa e attiva l'adapter YouTube (yt-dlp più Deno, il runtime JavaScript che yt-dlp richiede) |

Lo script è idempotente: puoi rieseguirlo per aggiornare. FFmpeg viene scaricato da
gyan.dev ("release essentials") e verificato con lo SHA-256 pubblicato.

> **⚠ Da verificare:** l'installazione completa è stata eseguita su un PC con la sola CPU e
> con un ambiente già parzialmente presente. Su un PC pulito e con l'opzione `-Runtime nvidia`
> non è ancora stata provata.

## Avvio

1. Fai doppio clic su **`LocalChords.bat`** nella cartella del progetto.
2. Si apre una finestra nativa. In alto un banner dice se è stata trovata una GPU NVIDIA
   utilizzabile.

Per vedere i log nel terminale (utile se qualcosa non va):

```powershell
.\LocalChords.bat --console
```

Chiudendo la finestra si fermano anche il server interno e il worker che elabora i brani.

Dati e log stanno in:

- `data\` — database SQLite, audio, stem, waveform, cache, modelli scaricati;
- `logs\` — log JSON (`app.log` per finestra e API, `worker.log` per le elaborazioni).

## Primo risultato: dal file agli accordi

Esempio concreto: hai un MP3 in `C:\Musica\brano.mp3` e vuoi gli accordi da suonare.

1. Avvia l'app con `LocalChords.bat`.
2. Trascina `brano.mp3` nella finestra (oppure **Scegli un file**). Formati ammessi: MP3, WAV,
   M4A, FLAC, OGG; fino a 500 MB; durata tra 3 secondi e 60 minuti.
3. Controlla l'anteprima: titolo, artista e album sono presi dai tag del file o dal nome
   (`Artista - Titolo.mp3`). Correggili se serve.
4. Premi **Importa**. Partono, senza altri clic:
   1. conversione in FLAC;
   2. analisi (beat, BPM, tonalità, accordi, sezioni);
   3. ricerca e allineamento del testo.
5. Quando lo stato diventa **Pronto**:
   - in alto compaiono tonalità e BPM;
   - sotto ci sono la waveform e gli **accordi per battuta**;
   - premi **Spazio** per ascoltare: l'accordo corrente si illumina.
6. Facoltativo:
   - **Trasponi** e **Capo** nella colonna destra adattano gli accordi alla tua voce o allo
     strumento;
   - **Esporta → PDF** salva lo spartito nella cartella Download.

> **⚠ Da verificare:**
> - durata dell'analisi su un brano reale;
> - qualità di accordi, beat e sezioni;
> - comportamento del trascinamento dei file nella finestra.
>
> Su un brano sintetico (C-G-Am-F a 120 BPM) l'analisi ha riconosciuto il 99% degli accordi,
> la tonalità e il BPM; su musica reale la qualità sarà più bassa e va misurata.

### La stessa cosa da riga di comando

Con l'app aperta, l'API locale risponde su `http://127.0.0.1:8765`. Se quella porta è
occupata l'app ne sceglie un'altra: la trovi in `data\instance.json`.

```powershell
$api = "http://127.0.0.1:8765/api"

# 1. Carica il file e ottieni l'anteprima
$up = Invoke-RestMethod -Method Post -Uri "$api/songs/upload" `
  -Headers @{ "X-Filename" = "brano.mp3" } `
  -ContentType "application/octet-stream" -InFile "C:\Musica\brano.mp3"
$up | Select-Object title, artist, duration_s, format

# 2. Conferma: crea il brano e avvia l'elaborazione
$body = @{ title = $up.title; artist = $up.artist } | ConvertTo-Json
$start = Invoke-RestMethod -Method Post -Uri "$api/songs/upload/$($up.upload_id)/confirm" `
  -ContentType "application/json" -Body $body

# 3. Controlla lo stato (ripeti finché status è "ready")
Invoke-RestMethod "$api/songs/$($start.song.id)" | Select-Object status, key, bpm

# 4. Leggi i primi accordi
(Invoke-RestMethod "$api/songs/$($start.song.id)/chords") |
  Select-Object -First 8 start_s, chord
```

> **Provato il 24/11/2026** con un brano sintetico di 25 s: stato `ready`, tonalità C,
> BPM 117,5, accordi C, G, Am, F. Le parentesi attorno a `Invoke-RestMethod` al punto 4 servono:
> con PowerShell 5.1, senza, la tabella degli accordi resta vuota.
>
> **⚠ Da verificare:** con PowerShell 5.1, titoli con lettere accentate potrebbero arrivare
> codificati male nel corpo JSON.

### Andare oltre

| Vuoi… | Dove |
|---|---|
| separare voce e strumenti | scheda del brano → **Stem → Separa in 6 stem** (la prima volta scarica il modello, circa 53 MB su CPU) |
| il testo sincronizzato | scheda del brano → **Testo**; per l'allineamento parola per parola serve il modello Whisper (464 MB, su richiesta) |
| esercitarti | barra in basso: velocità 0,5×–1,5×, tonalità ±11, loop A/B, metronomo, count-in |
| esportare | colonna destra → **Esporta** |
| cambiare tema | intestazione → **Tema**, oppure **Impostazioni → Aspetto** |
| liberare spazio | **Impostazioni → Spazio su disco** |

> **⚠ Da verificare:** separazione su GPU NVIDIA e qualità su brani reali. Su CPU sono stati
> provati con audio sintetico: separazione htdemucs_6s (16 s di audio in circa 23 s), tab dal
> basso, trascrizione Whisper small e allineamento del testo, export TXT/ChordPro/PDF/WAV/MP3
> e download dal browser.

## Importare un brano

1. Trascina un file audio nella finestra (o usa **Scegli un file**). Formati: MP3, WAV, M4A,
   FLAC, OGG; dimensione massima predefinita 500 MB (`LOCALCHORDS_MAX_UPLOAD_MB`).
2. L'app verifica il file e mostra un'anteprima: titolo, artista e album (dai tag o dal nome
   del file, nella forma "Artista - Titolo"), formato, durata, frequenza. Puoi correggerli.
3. **Importa** avvia l'elaborazione in background: verifica, conversione in FLAC 44,1 kHz
   stereo, controllo che l'audio non sia silenzioso. Puoi annullarla in qualsiasi momento.

Se lo stesso file (stesso SHA-256) è già nel catalogo, l'app lo segnala e propone di aprire
il brano esistente invece di rianalizzarlo.

Errori specifici: formato non supportato, file troppo grande, file vuoto o danneggiato,
nessuna traccia audio, brano troppo corto (< 3 s) o troppo lungo (> 60 min), audio
silenzioso, FFmpeg mancante. Un'importazione fallita o annullata si può riprovare.

### Da YouTube (facoltativo, disattivato di default)

`setup.ps1 -YouTube` installa yt-dlp e lo attiva (`LOCALCHORDS_YOUTUBE_ENABLED=true`). Nella
schermata di import compare il campo per il link: anteprima, conferma, download e poi la
stessa elaborazione dei file locali. Non usa account né cookie: video privati, con limiti
d'età o bloccati nel tuo paese danno un errore esplicito. Le dirette non sono supportate.

## Analisi

Parte da sola al termine dell'importazione (e si può rilanciare con **Rianalizza**):

| Risultato | Metodo attuale (profilo Leggero) |
|---|---|
| Beat, battute, BPM | librosa (programmazione dinamica sull'onset); primo battito scelto tra le 4 fasi con energia dei bassi e cambi armonici; 4/4 presunto |
| Accordi | chroma CQT per beat, 9 qualità per 12 fondamentali più rivolti, Viterbi (HMM) |
| Tonalità | profili di Krumhansl-Kessler più coerenza con gli accordi |
| Sezioni | novità sulla matrice di auto-somiglianza, etichette per ripetizione, nomi euristici |
| Waveform | picchi precalcolati (50 al secondo) |

Ogni valore ha un'indicazione di affidabilità. **L'accuratezza non è ancora stata misurata**:
il piano stima il 65-80% sugli accordi anche con i modelli neurali, e questi metodi classici
sono il fallback. Beat This!, BTC e SongFormer arriveranno con la gestione dei modelli
(fase 4). Quando esistono gli stem, gli accordi si calcolano sul mix senza voce e batteria.

## Separazione in 6 stem

Voce, batteria, basso, chitarra, pianoforte e altro. Gli stem servono per **studio e pratica
personale**. Dopo la separazione gli accordi vengono ricalcolati sul mix senza voce e batteria.

| Profilo | Modello | Dispositivo | Disponibile quando |
|---|---|---|---|
| Leggero | HT-Demucs 6 stem (~53 MB, MIT) | CPU | sempre (runtime installato) |
| Bilanciato | BS-RoFormer SW | DirectML | **non ancora supportato** |
| Massima qualità | BS-RoFormer SW (~668 MB, CC-BY-NC-SA-4.0, solo uso non commerciale) | GPU NVIDIA | GPU con almeno 8 GB e PyTorch CUDA |

- All'avvio un banner dice se c'è una GPU NVIDIA utilizzabile: con la GPU servono da pochi
  secondi a circa un minuto per brano, con la sola CPU 5-20 minuti.
- In **Impostazioni**: dispositivo (Automatico / GPU NVIDIA / Solo CPU), profilo, separazione
  automatica dopo l'import, download ed eliminazione dei modelli, spazio su disco.
- Il dispositivo si può cambiare anche per il singolo brano. Il tempo stimato si basa sulle
  misure reali dei brani già elaborati.
- I modelli si scaricano solo su richiesta, mostrando prima la dimensione. Se la separazione
  automatica è attiva e il modello è già scaricato, dopo l'import parte da sola.

## Testi sincronizzati

Dopo l'analisi (se non hai già modificato il testo):

1. **Ricerca** su LRCLIB (facoltativa, `LOCALCHORDS_LRCLIB_ENABLED`): si inviano solo titolo,
   artista, album e durata.
2. **Trascrizione** della voce con Whisper (faster-whisper), sullo stem della voce se esiste,
   altrimenti sul mix. Modello per profilo: small (464 MB, CPU), medium (1,46 GB),
   large-v3-turbo (1,55 GB, GPU). Si scarica solo su richiesta.
3. **Allineamento** parola per parola del testo trovato alle parole trascritte. Senza testo
   la trascrizione diventa il testo; senza modello Whisper restano i tempi per riga di LRCLIB.

Nella scheda del brano:
- **Karaoke**: riga e parola corrente evidenziate, accordi sopra le parole, scorrimento
  automatico, clic su una parola per ascoltare da lì.
- **Modifica**: testo e tempi di ogni riga e di ogni parola, "⏱" per impostare l'inizio alla
  posizione di ascolto, aggiungi ed elimina righe e parole, ripristina l'originale.
- **Annulla / Ripristina** (anche Ctrl+Z / Ctrl+Y): la cronologia è salvata nel database e
  sopravvive al riavvio. Ogni modifica si salva subito.
- **Incolla il testo** (anche in formato LRC) per sostituire quello trovato, poi allineamento.
- Brani strumentali e voce assente vengono segnalati.

## Interfaccia

Finestra da almeno 1280 px, su tre colonne:
- **sinistra**: importazione, coda di elaborazione, catalogo e sezioni del brano aperto;
- **centro**: tonalità e BPM, waveform, accordi, testo, tab, stem;
- **destra**: mixer, trasposizione / capo / semplificazione / notazione, diagrammi;
- **in basso**: barra di trasporto fissa.

Nell'intestazione: ricerca nel catalogo, stato del sistema, **tema** e impostazioni.

| Tema | Aspetto |
|---|---|
| Scuro | "studio", toni caldi, accento ambra (predefinito) |
| Chiaro | per ambienti luminosi |
| Cyber | nero e bordeaux, accenti turchese e giallo, angoli vivi, pannelli con l'angolo tagliato e una barra laterale; titoli in Bahnschrift (il font Neuromax del kit originale non è incluso per motivi di licenza) |
| Sistema | segue l'impostazione chiaro/scuro di Windows |

Il tema si sceglie dall'intestazione o da **Impostazioni → Aspetto** ed è ricordato tra le
sessioni. Contrasti WCAG AA in tutti i temi, focus visibile, collegamento "Vai al contenuto",
etichette ARIA, navigazione da tastiera; le animazioni si disattivano se Windows ha le
animazioni ridotte.

## Player e pratica

- **Mixer**: volume, mute e solo per ciascuno dei 6 stem (o per il mix completo se il brano
  non è separato), misuratori di livello e spia di clipping per traccia e sul master.
  Pulsanti rapidi "Solo voce", "Solo base", "Tutti".
- **Velocità** da 0,5× a 1,5× senza cambiare l'altezza e **tonalità** da -11 a +11 semitoni,
  indipendenti (SoundTouch in AudioWorklet).
- **Loop A/B**: trascina sulla waveform, oppure pulsanti A e B alla posizione attuale; con
  "snap" i punti si agganciano al beat più vicino. Maiusc+clic su un accordo ripete la sua
  battuta; "↻ ripeti" o Maiusc+clic sulla banda della waveform ripete una sezione.
- **Metronomo** sui beat dell'analisi, con volume e accento sul primo battito; **count-in**
  di 1, 2 o 4 battute prima di partire.
- Il testo scorre da solo seguendo la riproduzione.

| Tasto | Azione |
|---|---|
| Spazio | play / pausa |
| ← / → | indietro / avanti di 5 s (con Maiusc: una battuta) |
| 1-6 | seleziona una traccia del mixer |
| M / S | mute / solo della traccia selezionata |
| L | attiva o disattiva il loop (se non c'è, ripete la battuta corrente) |
| Ctrl+Z / Ctrl+Y | annulla / ripristina le modifiche al testo |

Memoria: i 6 stem decodificati occupano circa 500 MB per un brano di 4 minuti (44,1 kHz).

## Trasposizione, capo, semplificazione, diagrammi, tab

- **Trasposizione** da -11 a +11 semitoni con la tonalità risultante; la grafia (diesis o
  bemolle) segue la tonalità. L'originale compare sotto ogni accordo trasposto. "Applica
  all'audio" porta la tonalità del player allo stesso intervallo.
- **Capo** da 0 a 7: gli accordi diventano le forme da suonare. "Suggerito" indica il capo che
  riduce barré e posizioni alte (stima sulle diteggiature di chords-db, pesata per durata).
- **Semplificazione** su tre livelli: originale; intermedia (maj7, sus e aug diventano triadi,
  i rivolti perdono il basso); facile (anche 7, m7 e dim diventano maggiori o minori). Gli
  accordi semplificati hanno un bordo tratteggiato; selezionandone uno si legge il motivo e
  si può ripristinare solo quello (scelta salvata).
- **Notazioni**: americana (C, Am), italiana (Do, Lam), numerica (gradi rispetto alla tonalità).
- **Diagrammi** per chitarra e ukulele (diteggiature con numeri delle dita e barré, da
  chords-db) e pianoforte; quello dell'accordo corrente è evidenziato.
- **Vista compatta** (8 battute per riga) o estesa (4 battute, con l'accordo originale).
- **Tab di chitarra e basso** (indicative) dagli stem: note rilevate con il modello Basic
  Pitch (0,7 MB, scaricato al primo uso), corda e tasto scelti per la diteggiatura più comoda.
  Seguono trasposizione e capo.

Trasposizione, capo e semplificazione si salvano per brano; notazione, strumento e vista sono
preferenze generali.

## Esportazione

Pannello **Esporta** nella colonna destra della scheda del brano; i file vanno nella cartella
Download di Windows.

| Cosa | Formati | Note |
|---|---|---|
| Accordi e testo | PDF, TXT, ChordPro (`.cho`) | come mostrati: trasposizione, capo, semplificazione e notazione; titolo, artista, tonalità, capo, BPM |
| Tab | PDF | dal pannello Tab, chitarra o basso, con trasposizione e capo |
| Mix audio | MP3 320 kbit/s, WAV 16 bit | "come nel player": velocità, tonalità (Rubber Band) e mixer; il livello viene abbassato se andrebbe in clipping; MP3 con metadati |
| Stem | FLAC, singoli o ZIP | |

## Spazio su disco

In **Impostazioni → Spazio su disco**: occupazione di audio, stem, waveform, modelli, cache,
caricamenti non confermati, esportazioni e database; stem per brano con eliminazione; pulizia
di cache, caricamenti ed esportazioni. Gli stem sono salvati in FLAC.

## Configurazione

Copia `.env.example` in `.env` (lo fa `setup.ps1`) e modifica i valori. Tutte le variabili
sono documentate nel file d'esempio.

## Sviluppo

Usa sempre `python -m ...` invece degli eseguibili in `.venv\Scripts` (vedi
`docs\DECISIONI.md`: alcuni antivirus aziendali bloccano quei launcher). Con `uv run` indica
sempre il runtime installato (`--extra cpu` oppure `--extra nvidia`): senza, uv rimuove
PyTorch dall'ambiente.

```powershell
.\setup.ps1 -Dev                                   # una volta: include pytest, mypy, ruff
uv run --extra cpu python -m app.api.server --reload           # API su http://127.0.0.1:8765 (docs: /api/docs)
uv run --extra cpu python -m app.worker                        # worker dei job, in un secondo terminale
cd frontend; npm run dev                           # interfaccia con hot reload su http://localhost:5173
.\LocalChords.bat --console                        # app completa con i log nel terminale
```

Il server di sviluppo Vite inoltra `/api` alla porta 8765.

Test (audio sintetico generato al volo, nessuna canzone inclusa):

```powershell
uv run --extra cpu python -m pytest -m "not slow"    # veloci, circa 1 minuto
uv run --extra cpu python -m pytest -m slow          # modelli veri su CPU: scarica htdemucs_6s, Whisper small, Basic Pitch (~0,5 GB in tests\.slowdata)
cd frontend; npm test                                # Vitest: trasposizione, capo, notazioni, diagrammi
```

Test end-to-end dell'interfaccia (Playwright con Microsoft Edge): avvia l'app con almeno un
brano analizzato, poi `cd frontend; $env:E2E_URL = "http://127.0.0.1:8765"; npx playwright test`.
Senza l'app avviata i test falliscono con `ERR_CONNECTION_REFUSED`.

Controlli statici:

```powershell
uv run --extra cpu python -m mypy                    # tipi (strict)
uv run --extra cpu python -m ruff check .            # lint
uv run --extra cpu python -m app --smoke-test        # apre la finestra, verifica che l'interfaccia parta, chiude
cd frontend; npm run typecheck; npm run build
```

Nuova migrazione del database dopo aver modificato `app\db\models.py`:

```powershell
uv run --extra cpu python -m alembic revision --autogenerate -m "descrizione"
```

L'app applica le migrazioni da sola all'avvio.

## Architettura

Dal grafo del progetto, i nodi più collegati sono `Database`, `Job`, `Song`, `Settings`,
`AppError`, `JobQueue`. L'app è organizzata intorno a una **coda di lavori** su un
**database locale**:

| Componente | Cartella | Ruolo |
|---|---|---|
| Finestra desktop | `app/desktop.py` | avvia API e worker, apre la finestra (pywebview) |
| API | `app/api/` | endpoint `/api/...` usati dall'interfaccia |
| Coda e worker | `app/worker/` | elabora i brani in un processo separato; riprende dopo un'interruzione |
| Database | `app/db/` | SQLite in `data\localchords.db`, con migrazioni |
| Import | `app/importing/` | upload, verifica con FFmpeg, conversione in FLAC |
| Analisi | `app/analysis/` | beat, BPM, tonalità, accordi, sezioni, waveform |
| Separazione | `app/separation/` | 6 stem con audio-separator |
| Testi | `app/lyrics/` | LRCLIB, Whisper, allineamento, editor |
| Tab ed export | `app/tabs/`, `app/export/` | tab dagli stem; PDF, TXT, ChordPro, audio |
| Interfaccia | `frontend/` | React; player Web Audio in `frontend/src/audio/engine.ts` |

Struttura completa:

```
app\api\        FastAPI: router, schemi, errori strutturati {code, message, detail}
app\worker\     coda persistente su SQLite e processo worker (checkpoint per fase)
app\db\         modelli SQLAlchemy, sessioni, migrazioni Alembic
app\importing\  upload con anteprima, catalogo, job di importazione, validazione
app\analysis\   beat, accordi, tonalità, sezioni, waveform e job di analisi
app\separation\ modelli, separazione in un processo figlio, job di download e separazione
app\hardware.py rilevamento di GPU e runtime, profili
app\lyrics\     LRCLIB, Whisper in un processo figlio, allineamento, editor, job dei testi
app\editing\    cronologia persistente delle modifiche (annulla/ripristina)
app\tabs\       Basic Pitch in ONNX Runtime e assegnazione di corda e tasto
app\export\     spartito (TXT, ChordPro, PDF), tab in PDF, export audio
app\media\      wrapper di ffprobe e ffmpeg
app\storage\    struttura della cartella data\
app\adapters\   adapter YouTube (yt-dlp), facoltativo
app\desktop.py  avvio: migrazioni, API in un thread, worker in un processo, finestra pywebview
frontend\       Vite + React + TypeScript + Tailwind, compilato in statico e servito da FastAPI
```

### Coda dei job

- Stati: `queued`, `downloading`, `separating`, `analyzing`, `aligning`, `ready`, `failed`,
  `cancelled`.
- Un job in esecuzione salva un checkpoint dopo ogni fase. Se il worker si chiude o va in
  crash, il job torna in coda e riparte dall'ultima fase completata.
- I worker inviano un heartbeat; i job di un worker morto vengono recuperati
  automaticamente (dopo 3 tentativi falliti il job passa a `failed`).
- L'annullamento di un job in coda è immediato; per uno in esecuzione il worker si ferma
  al primo controllo utile.

### API disponibili

| Metodo | Percorso | Descrizione |
|---|---|---|
| GET | `/api/health` | stato di database, worker e FFmpeg |
| GET | `/api/jobs` | elenco dei job (filtro `?status=`) |
| GET | `/api/jobs/{id}` | stato, fase, progresso, tempo stimato, errore |
| POST | `/api/jobs/{id}/cancel` | annulla un job |
| GET | `/api/songs?q=` | catalogo, con ricerca su titolo, artista e album |
| POST | `/api/songs/upload` | corpo = byte del file, header `X-Filename`: verifica e anteprima |
| POST | `/api/songs/upload/{upload_id}/confirm` | crea il brano e accoda l'importazione |
| DELETE | `/api/songs/upload/{upload_id}` | scarta un'anteprima |
| POST | `/api/songs/import-url/preview` | anteprima di un video YouTube |
| POST | `/api/songs/import-url` | crea il brano da YouTube e accoda il download |
| GET / PATCH / DELETE | `/api/songs/{id}` | dettaglio, modifica di titolo/artista/album, eliminazione |
| POST | `/api/songs/{id}/retry` | riprova un'importazione fallita o annullata |
| GET | `/api/songs/{id}/audio` | audio normalizzato (FLAC), con supporto ai range |
| GET | `/api/songs/{id}/analysis` | BPM, tonalità, beat, accordi e sezioni con confidenza |
| GET | `/api/songs/{id}/chords` | solo gli accordi |
| GET | `/api/songs/{id}/waveform` | picchi della waveform (JSON) |
| POST | `/api/songs/{id}/analyze` | rilancia l'analisi (sostituisce i risultati) |
| GET | `/api/songs/{id}/separation-plan?device=` | modello, dispositivo e tempo stimato per la separazione |
| POST | `/api/songs/{id}/separate` | separa in 6 stem (`device`, `profile`, `allow_download`) |
| GET / DELETE | `/api/songs/{id}/stems` | elenco ed eliminazione degli stem |
| GET | `/api/songs/{id}/stems/{tipo}/audio` | singolo stem (FLAC) |
| GET | `/api/system/hardware` | CPU, RAM, GPU, runtime, profili e stime |
| GET / PUT | `/api/settings/processing` | dispositivo, profilo, separazione automatica |
| GET | `/api/models` | modelli con dimensione, licenza e stato |
| POST / DELETE | `/api/models/{id}` (`/download`) | scarica o elimina un modello |
| GET | `/api/system/storage` | occupazione su disco |
| POST | `/api/system/storage/cleanup` | svuota cache, caricamenti o esportazioni |
| GET | `/api/songs/{id}/lyrics` | righe e parole con tempi, stato, fonte, modello Whisper |
| PATCH / DELETE | `/api/songs/{id}/lyrics/{lineId}` | modifica (testo, inizio, fine) o elimina una riga |
| POST | `/api/songs/{id}/lyrics/lines` | aggiunge una riga |
| PATCH / DELETE | `/api/songs/{id}/lyrics/words/{wordId}` | modifica o elimina una parola |
| POST | `/api/songs/{id}/lyrics/{lineId}/words` | aggiunge una parola |
| POST | `/api/songs/{id}/lyrics/{lineId}/restore`, `/lyrics/restore` | ripristina l'originale (riga o tutto) |
| POST | `/api/songs/{id}/lyrics/refresh` | nuova ricerca o testo incollato (`text`, `search`) |
| POST | `/api/songs/{id}/undo`, `/redo` | annulla / ripristina l'ultima modifica |
| PATCH | `/api/songs/{id}/view` | trasposizione, capo, semplificazione del brano |
| PATCH | `/api/songs/{id}/chords/{chordId}` | modifica un accordo (`chord`, `simplify_exempt`) |
| POST | `/api/songs/{id}/chords/{chordId}/restore` | riporta l'accordo all'originale |
| GET / PUT | `/api/settings/display` | notazione, strumento, vista compatta |
| GET / POST | `/api/songs/{id}/tabs` | tab di chitarra e basso / generazione |
| POST | `/api/songs/{id}/export` | `pdf`, `txt`, `chordpro`, `tabs_pdf` (file subito) · `wav`, `mp3` (job) |
| GET | `/api/exports/{jobId}` | file del mix esportato |
| GET | `/api/songs/{id}/stems/{tipo}/download`, `/stems.zip` | stem singolo o tutti in ZIP |

Le anteprime di upload non confermate vengono eliminate dopo 24 ore.

## Grafo del progetto

Mappa del codice e dei documenti generata con [graphify](https://github.com/safishamsi/graphify).
Per esplorarla scarica il file `graph.html` e aprilo nel browser: GitHub ne mostra solo il sorgente.

| Versione | Contenuto | File |
|---|---|---|
| Completa | codice + documenti (brief, piano, decisioni), con collegamenti dedotti | [report](graphify-out/GRAPH_REPORT.md) · [graph.html](graphify-out/graph.html) · [graph.json](graphify-out/graph.json) |
| Solo codice, verificata | soli collegamenti `EXTRACTED` controllati riga per riga sui sorgenti; niente collegamenti dedotti né simboli esterni | [graph.html](graphify-codice/graphify-out/graph.html) · [graph.json](graphify-codice/graphify-out/graph.json) · [criteri e scarti](graphify-codice/graphify-out/verifica_filtro.json) |

La guida per chi inizia, in testa a questo file, è stata scritta a partire dal grafo e
verificata su `setup.ps1`, `LocalChords.bat`, `pyproject.toml`, `app/config.py` e sulle API.

## Risoluzione dei problemi

| Problema | Soluzione |
|---|---|
| `LocalChords non e' installato` | esegui `setup.ps1` |
| "Interfaccia non compilata" nella finestra | installa Node.js e riesegui `setup.ps1`, oppure `npm run build` in `frontend` |
| "LocalChords è già in esecuzione ma non risponde" | chiudi i processi `pythonw.exe` di LocalChords dal Task Manager, poi riavvia |
| La finestra non si apre | installa [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) e controlla `logs\app.log` |
| `uv` non trovato | `winget install astral-sh.uv`, poi riapri PowerShell |
| "Accesso negato" avviando `python.exe` del venv | un antivirus blocca il launcher: riesegui `setup.ps1`, che ricrea il venv con il launcher standard di CPython |
| FFmpeg mancante | riesegui `setup.ps1` senza `-SkipFfmpeg` |
| Errori senza spiegazione | avvia `LocalChords.bat --console` e guarda `logs\app.log` e `logs\worker.log` |

## Limiti noti

- **Test solo su CPU e audio sintetico**: separazione su CUDA (BS-RoFormer), Whisper su GPU
  e il profilo Massima qualità non sono ancora stati provati; nessun brano reale è stato
  elaborato da capo a fondo.
- **Accordi**: il backend attuale (chroma + HMM) è il fallback del piano; BTC non è ancora
  integrato. Accuratezza attesa sotto il 65-80% stimato per i modelli neurali: va misurata.
- **Beat e sezioni**: librosa; Beat This! e SongFormer non sono integrati. Metro 4/4 presunto.
- **Testi**: allineamento con faster-whisper + allineamento testuale (non WhisperX): tempi
  per parola meno precisi; serve l'editor.
- **Tab** indicative: corda e tasto sono stimati.
- **Separazione**: profilo Bilanciato (DirectML) non disponibile; chitarra e piano restano gli
  stem più deboli anche con BS-RoFormer.
- **Memoria**: il player tiene in RAM i 6 stem decodificati (~500 MB per 4 minuti).
- **Editor degli accordi**: si modifica il simbolo e si ripristina l'originale via API; dividere,
  unire e trascinare i confini degli accordi e delle sezioni dall'interfaccia non è ancora
  disponibile. BPM, offset della beat grid e tonalità non sono ancora modificabili.
- **Solo Windows 10/11 x64**, finestra da almeno 1280 px.

## Riepilogo dei punti da verificare

1. Installazione su un PC pulito e con GPU NVIDIA (`-Runtime nvidia`).
2. Elaborazione completa di un brano reale: import, analisi, testi, stem.
3. Qualità di accordi, beat, sezioni e allineamento dei testi.
4. Trascinamento dei file e download degli export nella finestra dell'app.
5. Sequenza di esempio da riga di comando con titoli accentati (PowerShell 5.1).
6. Tempi di elaborazione (le stime attuali sono valori iniziali).

I test automatici (pytest, Vitest, Playwright) girano su audio sintetico: non sostituiscono
la prova con brani reali. Le scelte tecniche e le loro motivazioni sono in `docs\DECISIONI.md`.

## Dipendenze esterne e licenze

| Componente | Uso | Licenza |
|---|---|---|
| FFmpeg (build gyan.dev) | decodifica, conversione, MP3 | GPL (build "essentials") |
| audio-separator, HT-Demucs | separazione | MIT |
| BS-RoFormer SW (pesi) | separazione, profilo Massima qualità | **CC-BY-NC-SA-4.0, solo uso non commerciale** |
| PyTorch | runtime della separazione | BSD |
| faster-whisper, modelli Whisper | trascrizione e allineamento | MIT |
| Basic Pitch (modello e algoritmo, portati) | note per le tab | Apache-2.0 |
| librosa, numpy, scipy, soundfile | analisi | ISC / BSD |
| pedalboard (Rubber Band) | velocità e tonalità nell'export | **GPL-3.0** |
| reportlab | PDF | BSD |
| yt-dlp (facoltativo) | import da YouTube | Unlicense |
| LRCLIB (servizio, facoltativo) | testi sincronizzati | servizio pubblico gratuito |
| @soundtouchjs/audio-worklet | velocità e tonalità nel player | MPL-2.0 |
| Tonal.js, chords-db, React, Tailwind, shadcn/ui, Radix | interfaccia e teoria | MIT |

Uniche chiamate di rete: download dei modelli e di FFmpeg (su richiesta), LRCLIB (se
attivo, solo titolo/artista/album/durata), YouTube (se attivato).

## Note legali

- La separazione degli stem è pensata per **studio e pratica personale**.
- I pesi del modello BS-RoFormer SW sono rilasciati con licenza **CC-BY-NC-SA-4.0**:
  solo uso non commerciale.
- L'app non include testi protetti né canzoni: parte vuota.
- Il download da YouTube è un adapter opzionale, **disattivato di default**.
