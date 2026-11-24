# LocalChords

App desktop **per Windows 10/11 (x64)**, local-first, che trasforma un file audio in accordi,
testi sincronizzati, tab, diagrammi e 6 stem con mixer e strumenti di pratica.
Tutto gira sul tuo PC: nessun account, nessun servizio cloud obbligatorio.

> **Stato:** fase 9 di 10. Scheletro, importazione da file locale (e da YouTube, se
> attivato), analisi (beat grid, BPM, tonalità, accordi, sezioni, waveform), separazione in
> 6 stem, rilevamento dell'hardware con profili, gestione dello spazio su disco e testi
> sincronizzati parola per parola con editor, player con mixer degli stem, velocità, tonalità,
> loop e metronomo, trasposizione, capo, semplificazione, notazioni, diagrammi, tab e interfaccia
> completa (tema scuro e chiaro, 3 colonne) ed export. Resta la verifica end-to-end (fase 10).
>
> I test automatici sono rimandati: verranno scritti ed eseguiti sul PC di test con GPU
> NVIDIA. Il codice delle fasi 2-9 è stato controllato solo staticamente (mypy, ruff, tsc):
> nessun brano è ancora stato importato, analizzato, separato, trascritto o riprodotto.

## Prerequisiti

| Strumento | Serve per | Note |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python isolato e dipendenze | `winget install astral-sh.uv` |
| [Node.js](https://nodejs.org/) 20+ | solo per compilare l'interfaccia | non serve in esecuzione |
| Microsoft Edge WebView2 | finestra dell'app | già incluso in Windows 11 |
| FFmpeg | decodifica e export audio | `setup.ps1` scarica una copia portabile in `tools\ffmpeg` |
| GPU NVIDIA (facoltativa) | elaborazione molto più veloce | senza GPU l'app usa il profilo "Leggero" su CPU |

Python **non** va installato a parte: `setup.ps1` fa scaricare a uv Python 3.12 dentro la
cartella dell'app (`.uv\python`), senza toccare quello di sistema.

## Installazione

Da PowerShell, nella cartella del progetto:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

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

## Avvio

Doppio clic su **`LocalChords.bat`**. Si apre una finestra nativa; alla chiusura si
fermano anche il server interno e il worker.

Dati e log stanno in:

- `data\` — database SQLite, audio, stem, waveform, cache, modelli scaricati;
- `logs\` — log JSON (`app.log` per finestra e API, `worker.log` per le elaborazioni).

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

Nell'intestazione: ricerca nel catalogo, stato del sistema, **tema** (Scuro "studio",
Chiaro o Sistema, ricordato tra le sessioni) e impostazioni. Contrasti WCAG AA in entrambi
i temi, focus visibile, collegamento "Vai al contenuto", etichette ARIA, navigazione da
tastiera; le animazioni si disattivano se Windows ha le animazioni ridotte.

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

### Da YouTube (facoltativo, disattivato di default)

`setup.ps1 -YouTube` installa yt-dlp e lo attiva (`LOCALCHORDS_YOUTUBE_ENABLED=true`). Nella
schermata di import compare il campo per il link: anteprima, conferma, download e poi la
stessa elaborazione dei file locali. Non usa account né cookie: video privati, con limiti
d'età o bloccati nel tuo paese danno un errore esplicito. Le dirette non sono supportate.

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

Controlli (i test automatici sono rimandati alla verifica sul PC di test con GPU NVIDIA):

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

## Risoluzione dei problemi

| Problema | Soluzione |
|---|---|
| "Interfaccia non compilata" nella finestra | esegui `setup.ps1` oppure `npm run build` in `frontend` |
| "LocalChords è già in esecuzione ma non risponde" | chiudi i processi `pythonw.exe` di LocalChords dal Task Manager, poi riavvia |
| La finestra non si apre | installa [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) e controlla `logs\app.log` |
| `uv` non trovato | `winget install astral-sh.uv`, poi riapri PowerShell |
| "Accesso negato" avviando `python.exe` del venv | un antivirus blocca il launcher: riesegui `setup.ps1`, che ricrea il venv con il launcher standard di CPython |
| Errori con i dettagli | avvia `LocalChords.bat --console` e guarda `logs\app.log` e `logs\worker.log` |

## Limiti noti

- **Nessun test automatico** nel repository: rimandati alla verifica sul PC con GPU NVIDIA.
  Dalla fase 2 in poi il codice è stato controllato solo staticamente; nessun brano reale è
  ancora stato elaborato da capo a fondo.
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
