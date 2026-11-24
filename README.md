# LocalChords: guida per iniziare

> Guida scritta a partire dal grafo del progetto (`graphify-out/GRAPH_REPORT.md`) e
> verificata su `setup.ps1`, `LocalChords.bat`, `pyproject.toml`, `app/config.py` e sulle API.
> I punti marcati **⚠ Da verificare** non sono ancora stati provati da capo a fondo. Il
> 24/11/2026 l'app è stata provata su un PC senza GPU con brani sintetici (accordi e voce
> generati al volo), non con brani reali.

## A cosa serve

LocalChords è un'app desktop per **Windows 10/11 (64 bit)**. Gli dai un file audio e ti
restituisce:

- **accordi** sincronizzati con la musica, per battuta;
- **testo** sincronizzato parola per parola (karaoke), modificabile;
- **6 stem** separati (voce, batteria, basso, chitarra, pianoforte, altro) con mixer;
- **strumenti di pratica**: velocità, tonalità, loop, metronomo, trasposizione, capo,
  diagrammi e tab;
- **export** in PDF, TXT, ChordPro, MP3/WAV.

Tutto avviene sul tuo PC: nessun account e nessun servizio cloud obbligatorio.

## Prima di iniziare

Ti servono:

| Cosa | Perché | Come averlo |
|---|---|---|
| Windows 10 o 11, 64 bit | unico sistema supportato | — |
| uv | installa Python e le dipendenze | `setup.ps1` prova a installarlo con winget |
| Node.js 20 o superiore | compila l'interfaccia (solo durante l'installazione) | `winget install OpenJS.NodeJS.LTS` |
| WebView2 | mostra la finestra dell'app | già presente in Windows 11 |
| Connessione internet | download di Python, librerie, FFmpeg e modelli | solo per l'installazione e i modelli |
| GPU NVIDIA (facoltativa) | separazione molto più veloce | senza GPU funziona tutto, ma più lentamente |

Python **non** va installato a parte: lo script lo scarica dentro la cartella dell'app.

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

```powershell
.\setup.ps1 -Runtime cpu      # forza la sola CPU (o: nvidia, auto)
.\setup.ps1 -YouTube          # aggiunge l'import da link YouTube (disattivato di default)
.\setup.ps1 -Dev              # aggiunge gli strumenti di sviluppo
```

> **⚠ Da verificare:** l'installazione completa è stata eseguita su un PC con la sola CPU e
> con un ambiente già parzialmente presente. Su un PC pulito e con l'opzione `-Runtime nvidia`
> non è ancora stata provata.

## Avvio

1. Fai doppio clic su **`LocalChords.bat`** nella cartella del progetto.
2. Si apre la finestra di LocalChords. In alto un banner dice se è stata trovata una GPU
   NVIDIA utilizzabile.

Per vedere i log nel terminale (utile se qualcosa non va):

```powershell
.\LocalChords.bat --console
```

Chiudendo la finestra si fermano anche il server interno e il processo che elabora i brani.

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
> **⚠ Da verificare:** con PowerShell 5.1, titoli con lettere accentate potrebbero arrivare codificati male nel
> corpo JSON.

## Andare oltre

| Vuoi… | Dove |
|---|---|
| separare voce e strumenti | scheda del brano → **Stem → Separa in 6 stem** (la prima volta scarica il modello, circa 53 MB su CPU) |
| il testo sincronizzato | scheda del brano → **Testo**; per l'allineamento parola per parola serve il modello Whisper (464 MB, su richiesta) |
| esercitarti | barra in basso: velocità 0,5×–1,5×, tonalità ±11, loop A/B, metronomo, count-in |
| esportare | colonna destra → **Esporta** |
| liberare spazio | **Impostazioni → Spazio su disco** |

> **⚠ Da verificare:** separazione su GPU NVIDIA e qualità su brani reali. Su CPU sono stati
> provati con audio sintetico: separazione htdemucs_6s (16 s di audio in circa 23 s), tab dal
> basso, trascrizione Whisper small e allineamento del testo, export TXT/ChordPro/PDF/WAV/MP3
> e download dal browser.

## Componenti principali

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

I tuoi dati stanno in `data\`, i log in `logs\` (`app.log`, `worker.log`).

## Se qualcosa non va

| Problema | Cosa fare |
|---|---|
| `LocalChords non e' installato` | esegui `setup.ps1` |
| "Interfaccia non compilata" | installa Node.js e riesegui `setup.ps1` |
| "Accesso negato" avviando Python | un antivirus blocca il venv: riesegui `setup.ps1`, che lo ricrea |
| FFmpeg mancante | riesegui `setup.ps1` senza `-SkipFfmpeg` |
| errori senza spiegazione | avvia con `LocalChords.bat --console` e leggi `logs\app.log` e `logs\worker.log` |

## Riepilogo dei punti da verificare

1. Installazione su un PC pulito e con GPU NVIDIA (`-Runtime nvidia`).
2. Elaborazione completa di un brano reale: import, analisi, testi, stem.
3. Qualità di accordi, beat, sezioni e allineamento dei testi.
4. Trascinamento dei file e download degli export nella finestra dell'app.
5. Sequenza di esempio da riga di comando.
6. Tempi di elaborazione (le stime attuali sono valori iniziali).

Non ci sono ancora test automatici: sono previsti per la verifica finale. I dettagli tecnici
e i limiti noti sono in `README.md` e in `docs/DECISIONI.md`.
