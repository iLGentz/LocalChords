# LocalChords — piano tecnico approvato

Decisioni prese il 24/11/2026, che sostituiscono le parti corrispondenti di `BRIEF_ORIGINALE.md`.

## 1. Decisioni di prodotto
- **Solo PC Windows** (10/11 x64). Niente layout mobile o tablet. Larghezza minima circa 1280 px, layout a 3 colonne.
- **Nessuna canzone demo.** L'app parte vuota con uno stato vuoto curato ("Trascina qui un file audio").
- **Tutto modificabile dopo la generazione:** accordi (simbolo, divisione e unione, confini trascinabili, inserisci ed elimina), testi (righe e parole), tempi di righe e parole, sezioni (nome, colore, confini), BPM, offset della beat grid, tonalità, trasposizione, capo, livello di semplificazione.
  - Ogni entità conserva il valore originale dell'analisi e quello corrente.
  - Annulla e ripristina, con cronologia persistente (tabella `edit_history`).
  - "Ripristina originale" per ogni elemento e per l'intero brano.
  - Salvataggio automatico in SQLite.
- **Avviso hardware:** all'avvio l'app rileva GPU NVIDIA e VRAM (`nvidia-smi`, `torch.cuda` o provider ONNX Runtime disponibili). Un banner spiega che con una GPU NVIDIA l'elaborazione è molto più veloce (secondi o circa 1 minuto per brano) e che con la sola CPU è più lenta (5–20 minuti). Selettore **Auto / GPU NVIDIA / Solo CPU** nelle impostazioni, modificabile anche per singolo job. Il tempo stimato si ricalcola dalla scelta e dalle misure reali salvate.
- L'**adapter YouTube** (yt-dlp) è opzionale e **disattivato di default**. La modalità "solo file locali" è pienamente funzionante.
- Note legali nell'interfaccia: gli stem servono per studio e pratica personale. I pesi di BS-RoFormer SW sono CC-BY-NC-SA-4.0 (solo uso non commerciale).

## 2. Stack (cambi rispetto al brief già approvati)
| Area | Scelta | Al posto di |
|---|---|---|
| Distribuzione | **Installazione nativa con `uv`**: Python 3.12 isolato (era 3.11, cambiato il 24/11/2026: vedi docs/DECISIONI.md) nella cartella dell'app, `setup.ps1` e `LocalChords.bat` | Docker Compose |
| Shell desktop | **pywebview** (Edge WebView2) che apre la UI in una finestra nativa | Browser |
| Frontend | **Vite + React + TypeScript**, Tailwind, shadcn/ui, compilato in statico e servito da FastAPI | Next.js |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, SQLite | (invariato) |
| Coda job | **Coda persistente su SQLite** con un processo worker separato | Redis |
| Inferenza | **ONNX Runtime dove esiste un ONNX affidabile** (DirectML per tutte le GPU, CUDA EP per NVIDIA). PyTorch solo per i componenti senza ONNX | PyTorch ovunque |
| Audio nel player | Web Audio: 6 GainNode → AudioWorklet **SoundTouch** (velocità e tonalità indipendenti), metronomo con oscillatori schedulati | Solo Wavesurfer |
| Waveform | Wavesurfer.js con il plugin regions per sezioni e loop | (invariato) |
| Teoria musicale | Tonal.js più **chords-db** (MIT) per le diteggiature di chitarra e ukulele (dita, barré). Pianoforte disegnato da codice | (invariato più chords-db) |
| Export audio | FFmpeg più **pedalboard** (Rubber Band) per velocità e tonalità nel mix esportato | — |
| PDF | reportlab | — |

### Modelli per componente
| Componente | Massima qualità | Leggero / fallback |
|---|---|---|
| Separazione 6 stem | **BS-RoFormer SW** (`audio-separator` oppure ONNX) | **htdemucs_6s** (ONNX) |
| Beat, downbeat, BPM | **Beat This!** (CPJKU, MIT; ONNX disponibile) | librosa |
| Accordi | **BTC, vocabolario esteso**, eseguito sul mix bass+guitar+piano+other (senza voce e batteria) e allineato alla beat grid | `lv-chordia`, oppure chroma con HMM |
| Tonalità | Profili di chroma più coerenza con la sequenza di accordi, con confidenza | — |
| Sezioni | **SongFormer** (opzionale, pesante) | Segmentazione librosa con euristiche sulle ripetizioni |
| Testi | **LRCLIB** (opzionale, disattivabile) più allineamento **WhisperX** (wav2vec2 CTC) sullo stem della voce. Senza testo disponibile: trascrizione con faster-whisper | Whisper small int8 |
| Tab | **basic-pitch** sugli stem di chitarra e basso, con assegnazione corda e tasto tramite programmazione dinamica. Nell'interfaccia: "tab indicative" | — |

## 3. Profili hardware (scelta automatica, modificabile)
| Profilo | Separazione | Whisper | Sezioni | Predefinito per |
|---|---|---|---|---|
| **Leggero** | htdemucs_6s ONNX su CPU | small int8 | librosa | PC senza GPU |
| **Bilanciato** | BS-RoFormer SW su ONNX DirectML | medium | librosa | Qualsiasi GPU DX12 (AMD, Intel, NVIDIA) |
| **Massima qualità** | BS-RoFormer SW su CUDA | large-v3-turbo | SongFormer | NVIDIA con almeno 8 GB di VRAM |

- I modelli si scaricano **su richiesta**, solo quelli del profilo scelto, mostrando prima la dimensione. Si possono eliminare dalle impostazioni.
- `setup.ps1` chiede (o rileva) **CPU** oppure **NVIDIA** e installa solo il runtime necessario: PyTorch CPU, CUDA o nessun PyTorch se bastano i modelli ONNX.

## 4. Ottimizzazione del peso
- Stem salvati in **FLAC**. WAV e MP3 si generano solo in export.
- Frontend compilato in statico: Node serve solo per il build, non in esecuzione.
- PyTorch come extra opzionale. Ogni componente convertito in ONNX e verificato rimuove una dipendenza da PyTorch.
- Pagina "Spazio su disco": occupazione di audio, stem, cache e modelli, con pulizia selettiva.

## 5. Architettura
```
LocalChords/
  app/                  # pacchetto Python
    api/                # FastAPI: router, schemi Pydantic, errori strutturati
    worker/             # worker dei job (processo separato), checkpoint per fase
    db/                 # modelli SQLAlchemy, sessioni; migrations/ (Alembic)
    storage/            # gestione di data/ (audio, stem, waveform, cache, modelli)
    analysis/           # beat, tonalità, accordi, sezioni, waveform
    separation/         # interfaccia Separator più backend (roformer, htdemucs)
    lyrics/             # adapter LRCLIB, allineamento, trascrizione
    export/             # PDF, TXT, ChordPro, mix WAV/MP3, stem
    adapters/youtube.py # yt-dlp, disattivato di default
    hardware.py         # rilevamento GPU, profili, stime dei tempi
    desktop.py          # avvio con pywebview
  frontend/             # Vite + React + TS
  tests/                # pytest
  data/  logs/          # creati in esecuzione, esclusi da git
  setup.ps1  LocalChords.bat  .env.example  README.md
```
- Stati dei job: `queued, downloading, separating, analyzing, aligning, ready, failed` (più `cancelled`). Progresso reale, fase corrente, tempo stimato e messaggio di errore utile.
- Il worker è ripristinabile: un job interrotto riparte dall'ultima fase completata.
- Cache per checksum SHA-256: lo stesso file non viene rianalizzato.
- Errori API strutturati `{code, message, detail}`, senza stack trace verso il frontend. Log JSON in `logs/`.
- Endpoint: quelli del brief, più PATCH, POST e DELETE per sezioni e parole, `/api/system/hardware`, `/api/system/storage`, `/api/models`, undo e redo.

## 6. Fasi (test e resoconto dopo ognuna)
1. Scheletro: pacchetto, configurazione, database, migrazioni, coda job, worker, `/api/health`, `setup.ps1`, `LocalChords.bat`, finestra pywebview vuota, README.
2. Import di file locali: validazione, checksum e cache, metadati, annullamento, errori specifici. Poi l'adapter YouTube.
3. Analisi: beat e downbeat, BPM, tonalità, accordi, sezioni, waveform.
4. Separazione in 6 stem, rilevamento hardware e profili, gestione dello spazio su disco.
5. Testi: LRCLIB, allineamento parola per parola, trascrizione di fallback, editor.
6. Player: Web Audio, SoundTouch, mixer con mute e solo, clipping, loop A/B con snap, metronomo, count-in, scorciatoie.
7. Trasposizione da -11 a +11, capo, semplificazione su 3 livelli con spiegazione, notazioni americana, italiana e numerica, diagrammi, tab.
8. Interfaccia completa: tema studio scuro e tema chiaro, accessibilità WCAG AA, skeleton, stati vuoti.
9. Export e test (pytest, Vitest, Playwright), README completo, limiti noti.
10. Verifica end-to-end sulla 3080 Ti e in modalità solo CPU.

## 7. Rischi noti
- Accuratezza degli accordi realistica tra il 65% e l'80% su pop e rock: va dichiarata. Da qui l'importanza dell'editor.
- Gli stem di piano e chitarra restano i più deboli anche con BS-RoFormer.
- RAM: 6 stem decodificati nel browser occupano circa 500 MB. Valutare la decodifica a 44,1 kHz con caricamento progressivo.
- Le conversioni in ONNX vanno verificate numericamente contro PyTorch su più brani prima di renderle predefinite.
