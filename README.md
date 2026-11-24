# LocalChords

App desktop **per Windows 10/11 (x64)**, local-first, che trasforma un file audio in accordi,
testi sincronizzati, tab, diagrammi e 6 stem con mixer e strumenti di pratica.
Tutto gira sul tuo PC: nessun account, nessun servizio cloud obbligatorio.

> **Stato:** fase 1 di 10 (scheletro). Database, coda dei job, worker, API di sistema e
> finestra desktop funzionano; import, analisi, separazione e player arrivano nelle fasi
> successive (vedi `PIANO.md`).

## Prerequisiti

| Strumento | Serve per | Note |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python isolato e dipendenze | `winget install astral-sh.uv` |
| [Node.js](https://nodejs.org/) 20+ | solo per compilare l'interfaccia | non serve in esecuzione |
| Microsoft Edge WebView2 | finestra dell'app | già incluso in Windows 11 |
| FFmpeg | decodifica e export audio | `setup.ps1` scarica una copia portabile in `tools\ffmpeg` |
| GPU NVIDIA (facoltativa) | elaborazione molto più veloce | senza GPU l'app usa il profilo "Leggero" su CPU |

Python **non** va installato a parte: `setup.ps1` fa scaricare a uv Python 3.11 dentro la
cartella dell'app (`.uv\python`), senza toccare quello di sistema.

## Installazione

Da PowerShell, nella cartella del progetto:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Opzioni utili:

| Opzione | Effetto |
|---|---|
| `-Runtime auto\|cpu\|nvidia` | runtime di inferenza da installare (predefinito `auto`: rileva `nvidia-smi`) |
| `-SkipFfmpeg` | non scarica FFmpeg (se lo hai già nel PATH o lo installerai dopo) |
| `-SkipFrontend` | non ricompila l'interfaccia |
| `-Dev` | installa anche gli strumenti di sviluppo (pytest, mypy, ruff) |

Lo script è idempotente: puoi rieseguirlo per aggiornare. FFmpeg viene scaricato da
gyan.dev ("release essentials") e verificato con lo SHA-256 pubblicato.

## Avvio

Doppio clic su **`LocalChords.bat`**. Si apre una finestra nativa; alla chiusura si
fermano anche il server interno e il worker.

Dati e log stanno in:

- `data\` — database SQLite, audio, stem, waveform, cache, modelli scaricati;
- `logs\` — log JSON (`app.log` per finestra e API, `worker.log` per le elaborazioni).

## Configurazione

Copia `.env.example` in `.env` (lo fa `setup.ps1`) e modifica i valori. Tutte le variabili
sono documentate nel file d'esempio.

## Sviluppo

Usa sempre `python -m ...` invece degli eseguibili in `.venv\Scripts` (vedi
`docs\DECISIONI.md`: alcuni antivirus aziendali bloccano quei launcher).

```powershell
.\setup.ps1 -Dev                                   # una volta: include pytest, mypy, ruff
uv run python -m app.api.server --reload           # API su http://127.0.0.1:8765 (docs: /api/docs)
uv run python -m app.worker                        # worker dei job, in un secondo terminale
cd frontend; npm run dev                           # interfaccia con hot reload su http://localhost:5173
.\LocalChords.bat --console                        # app completa con i log nel terminale
```

Il server di sviluppo Vite inoltra `/api` alla porta 8765.

Controlli (i test automatici sono rimandati alla verifica sul PC di test con GPU NVIDIA):

```powershell
uv run python -m mypy                    # tipi (strict)
uv run python -m ruff check .            # lint
uv run python -m app --smoke-test        # apre la finestra, verifica che l'interfaccia parta, chiude
cd frontend; npm run typecheck; npm run build
```

Nuova migrazione del database dopo aver modificato `app\db\models.py`:

```powershell
uv run python -m alembic revision --autogenerate -m "descrizione"
```

L'app applica le migrazioni da sola all'avvio.

## Architettura

```
app\api\        FastAPI: router, schemi, errori strutturati {code, message, detail}
app\worker\     coda persistente su SQLite e processo worker (checkpoint per fase)
app\db\         modelli SQLAlchemy, sessioni, migrazioni Alembic
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

### API disponibili (fase 1)

| Metodo | Percorso | Descrizione |
|---|---|---|
| GET | `/api/health` | stato di database, worker e FFmpeg |
| GET | `/api/jobs` | elenco dei job (filtro `?status=`) |
| GET | `/api/jobs/{id}` | stato, fase, progresso, tempo stimato, errore |
| POST | `/api/jobs/{id}/cancel` | annulla un job |

## Risoluzione dei problemi

| Problema | Soluzione |
|---|---|
| "Interfaccia non compilata" nella finestra | esegui `setup.ps1` oppure `npm run build` in `frontend` |
| "LocalChords è già in esecuzione ma non risponde" | chiudi i processi `pythonw.exe` di LocalChords dal Task Manager, poi riavvia |
| La finestra non si apre | installa [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) e controlla `logs\app.log` |
| `uv` non trovato | `winget install astral-sh.uv`, poi riapri PowerShell |
| "Accesso negato" avviando `python.exe` del venv | un antivirus blocca il launcher: riesegui `setup.ps1`, che ricrea il venv con il launcher standard di CPython |
| Errori con i dettagli | avvia `LocalChords.bat --console` e guarda `logs\app.log` e `logs\worker.log` |

## Note legali

- La separazione degli stem è pensata per **studio e pratica personale**.
- I pesi del modello BS-RoFormer SW sono rilasciati con licenza **CC-BY-NC-SA-4.0**:
  solo uso non commerciale.
- L'app non include testi protetti né canzoni: parte vuota.
- Il download da YouTube è un adapter opzionale, **disattivato di default**.
