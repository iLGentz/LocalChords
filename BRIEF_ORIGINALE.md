Sei un senior full-stack engineer e product designer. Devi costruire da zero un clone locale, funzionalmente equivalente a Song2Chord, con un'interfaccia moderna e curata. Non è un prototipo: voglio un'app completa, avviabile in locale con un solo comando, utilizzabile su macOS, Windows e Linux.

## Obiettivo

Crea "LocalChords", un'app web local-first che trasformi un link YouTube o un file audio caricato dall'utente in:

- accordi sincronizzati con la canzone;
- testi sincronizzati parola per parola;
- tablature per chitarra e basso;
- diagrammi di accordi per chitarra, ukulele e pianoforte;
- separazione della traccia in 6 stem: voce, batteria, basso, chitarra, pianoforte, altro;
- mixer con mute, solo e volume per ogni stem;
- player con velocità variabile, cambio tonalità, loop di sezioni, metronomo e count-in;
- trasposizione degli accordi, suggerimento capo e semplificazione degli accordi.

L'app deve funzionare interamente in locale. Nessun servizio cloud obbligatorio, nessuna API a pagamento, nessun dato dell'utente inviato all'esterno. Le uniche chiamate esterne ammesse sono quelle strettamente necessarie per recuperare metadati o testi, e devono essere opzionali e sostituibili.

## Vincoli legali e di prodotto

- Non copiare branding, logo, testi, asset o layout proprietari di Song2Chord. Replica le funzionalità, non l'identità visiva.
- Il download da YouTube deve essere un adapter opzionale e disattivabile.
- Prevedi una modalità "solo file locali" pienamente funzionante, senza YouTube.
- Non aggirare DRM, paywall o limitazioni tecniche.
- La separazione degli stem è per studio e pratica personale: inserisci questa nota nell'interfaccia.

## Stack consigliato

Scegli una combinazione semplice da avviare in locale e ben supportata:

- Frontend: Next.js con TypeScript, Tailwind CSS e shadcn/ui.
- Backend: FastAPI in Python, perché l'ecosistema audio è più maturo.
- Database: SQLite con SQLAlchemy e Alembic.
- Storage: cartella locale `data/` per audio, stem, waveform e cache.
- Player e waveform: Wavesurfer.js.
- Teoria musicale: Tonal.js per trasposizione, capo, semplificazione e diagrammi.
- Analisi audio: Librosa, Madmom o Basic Pitch per BPM, tonalità, beat grid e accordi.
- Separazione stem: Demucs con modello a 6 stem.
- Download audio: yt-dlp, isolato in un adapter.
- Conversione audio: FFmpeg.
- Job queue: worker Python con Redis oppure una coda persistente su SQLite, senza dipendenze cloud.
- Test: Vitest e Playwright per il frontend, Pytest per il backend.
- Avvio: Docker Compose con un comando unico, più una modalità sviluppo senza Docker.

Se una libreria non è disponibile o non è adatta, proponi un'alternativa motivata prima di implementarla. Non cambiare stack senza spiegare il motivo.

## Architettura richiesta

Separa chiaramente:

1. Frontend React.
2. API FastAPI.
3. Worker di elaborazione audio.
4. Database SQLite.
5. Storage locale dei file.
6. Modulo di analisi musicale.
7. Modulo di separazione stem.
8. Modulo di recupero e allineamento testi.
9. Modulo di esportazione.

Ogni elaborazione pesante deve girare come job asincrono con stati: `queued`, `downloading`, `separating`, `analyzing`, `aligning`, `ready`, `failed`. Il frontend deve mostrare progresso reale, fase corrente, tempo stimato e messaggio di errore utile. Non bloccare mai l'interfaccia durante l'analisi.

## Modello dati minimo

Prevedi almeno queste entità:

- Song: id, titolo, artista, album, durata, tonalità, BPM, source type, source URL, data di creazione, stato.
- AudioAsset: id, song id, percorso file, formato, durata, checksum.
- Stem: id, song id, tipo, percorso, volume predefinito, stato.
- ChordEvent: id, song id, start time, end time, accordo originale, accordo corrente, confidenza, beat.
- LyricLine: id, song id, testo, start time, end time.
- LyricWord: id, lyric line id, testo, start time, end time.
- TabNote: id, song id, strumento, corda, tasto, start time, durata.
- Section: id, song id, nome, start time, end time, colore.
- UserPreference: tema, volume, strumento preferito, notazione, ecc.

Usa migrazioni versionate. Non salvare dati derivati solo in memoria se devono sopravvivere al riavvio.

## Funzionalità dettagliate

### 1. Inserimento canzone

- Campo per incollare un link YouTube.
- Drag and drop o selettore per file audio: MP3, WAV, M4A, FLAC, OGG.
- Ricerca nel catalogo locale per titolo, artista e album.
- Validazione del link e del file.
- Anteprima dei metadati prima di avviare l'analisi.
- Possibilità di annullare un job.
- Messaggi di errore specifici: link non valido, video non disponibile, file troppo grande, formato non supportato, audio senza tracce sufficienti.

### 2. Analisi audio

- Rilevamento BPM e tonalità con indicazione di confidenza.
- Beat grid e downbeat.
- Rilevamento accordi per battuta e per evento.
- Rilevamento delle sezioni: intro, strofa, ritornello, bridge, outro, con nomi modificabili.
- Allineamento dei testi alla voce.
- Generazione waveform e marker delle sezioni.
- Cache dei risultati per non rianalizzare lo stesso file.

### 3. Separazione stem

- Genera 6 stem: vocals, drums, bass, guitar, piano, other.
- Mixer con slider volume, mute e solo per stem.
- Possibilità di ascoltare solo la voce o solo la base.
- Indicatore di clipping.
- Esportazione del mix in WAV o MP3.
- Possibilità di scaricare i singoli stem.
- Gestione chiara dello spazio su disco e pulsante per eliminare gli stem.

### 4. Visualizzazione accordi

- Accordi sopra il testo, allineati alla timeline.
- Evidenziazione dell'accordo corrente durante la riproduzione.
- Click su un accordo per ascoltare la battuta o impostare il loop.
- Diagrammi di accordi per chitarra, ukulele e pianoforte.
- Diteggiature con numeri delle dita e barré.
- Tablature per chitarra e basso.
- Notazione alternativa: americana, italiana, numerica.
- Modalità compatta e modalità estesa.

### 5. Testi e karaoke

- Testo sincronizzato riga per riga.
- Modalità karaoke con evidenziazione parola per parola.
- Possibilità di correggere manualmente il testo e i timing.
- Editor semplice: sposta l'inizio di una riga, aggiungi o rimuovi una parola, correggi un timestamp.
- Salvataggio automatico delle modifiche.
- Nessun testo protetto incluso di default.

### 6. Trasposizione e capo

- Trasposizione da -11 a +11 semitoni.
- Visualizzazione della tonalità risultante.
- Suggerimento del capo che riduce barré e accordi difficili.
- Applicazione simultanea a accordi, tab e diagrammi.
- Indicazione degli accordi originali accanto a quelli trasposti.
- Reset rapido alla tonalità originale.

### 7. Semplificazione accordi

- Sostituzione di accordi complessi con maggiori e minori equivalenti.
- Livelli: originale, intermedio, facile.
- Evidenziazione degli accordi sostituiti.
- Possibilità di ripristinare il singolo accordo.
- Spiegazione del perché un accordo è stato semplificato.

### 8. Player e pratica

- Play, pausa, stop.
- Velocità da 0.5x a 1.5x senza cambiare l'altezza.
- Cambio tonalità dell'audio da -11 a +11 semitoni.
- Loop A/B con snap alla battuta.
- Loop di una sezione.
- Metronomo con volume e accento sul primo battito.
- Count-in di 1, 2 o 4 battute.
- Scorri automatico del testo.
- Scorciatoie da tastiera: spazio per play/pausa, frecce per spostarsi, M per mute, S per solo, L per loop.

### 9. Interfaccia

Crea un'interfaccia premium, pulita e riconoscibile, non un template generico.

Direzione visiva:
- Tema scuro "studio" come default, con tema chiaro opzionale.
- Sfondo antracite caldo, superfici leggermente elevate, bordi sottili.
- Accento principale ambra o teal, usato con parsimonia.
- Tipografia sans-serif moderna per l'interfaccia e monospace per accordi e tab.
- Accordi come chip compatti, con stato attivo ben visibile.
- Waveform ampia e leggibile, con sezioni colorate.
- Transport bar sticky in basso, sempre accessibile.
- Pannello laterale per stem, tonalità, capo e semplificazione.
- Layout responsive: desktop a tre colonne, tablet a due, mobile a colonna singola.
- Animazioni brevi e funzionali, mai decorative o lente.
- Stati vuoti curati, skeleton loader e messaggi di errore comprensibili.
- Accessibilità: contrasto WCAG AA, focus visibile, navigazione da tastiera, etichette ARIA.

Struttura schermata principale:
- Header con logo, ricerca, tema e impostazioni.
- Colonna sinistra: coda, catalogo e sezioni.
- Colonna centrale: player, waveform, accordi e testo.
- Colonna destra: stem mixer, tonalità, capo, semplificazione e diagrammi.
- Barra inferiore: trasporto, velocità, volume, loop e metronomo.

### 10. Esportazione

- Esporta accordi e testo in PDF.
- Esporta accordi in formato testo e ChordPro.
- Esporta tab in PDF.
- Esporta il mix audio in WAV o MP3.
- Esporta i singoli stem.
- Includi metadati: titolo, artista, tonalità, capo, BPM.

## API minime

Prevedi endpoint REST chiari:

- `POST /api/songs/import-url`
- `POST /api/songs/upload`
- `GET /api/songs`
- `GET /api/songs/{id}`
- `DELETE /api/songs/{id}`
- `GET /api/jobs/{id}`
- `POST /api/jobs/{id}/cancel`
- `GET /api/songs/{id}/chords`
- `GET /api/songs/{id}/lyrics`
- `GET /api/songs/{id}/stems`
- `PATCH /api/songs/{id}/chords/{chordId}`
- `PATCH /api/songs/{id}/lyrics/{lineId}`
- `POST /api/songs/{id}/export`
- `GET /api/health`

Usa validazione rigorosa con Pydantic. Restituisci errori strutturati con codice, messaggio e dettaglio. Non esporre stack trace al frontend.

## Qualità e affidabilità

- Gestisci file corrotti, audio senza voce, brani strumentali e link non disponibili.
- Non perdere il lavoro se il worker si riavvia: i job devono essere ripristinabili.
- Limita l'uso di CPU e RAM configurabile.
- Mostra spazio occupato e permetta la pulizia della cache.
- Log strutturati e cartella `logs/`.
- Nessun segreto nel repository.
- `.env.example` completo.
- README con prerequisiti, installazione, avvio, risoluzione problemi e note legali.
- Script di setup per macOS, Linux e Windows.
- Docker Compose con volumi persistenti.
- Modalità demo con una canzone royalty-free inclusa, così l'app è testabile senza YouTube.

## Criteri di accettazione

L'app è completa solo se:

1. Si avvia con un comando e si apre nel browser senza passaggi manuali nascosti.
2. Carica un file audio locale e completa l'analisi con progresso visibile.
3. Mostra accordi e testo sincronizzati durante la riproduzione.
4. Separa l'audio in 6 stem e permette mute, solo e volume indipendenti.
5. Trasporta gli accordi da -11 a +11 semitoni e aggiorna i diagrammi.
6. Suggerisce un capo e lo applica correttamente.
7. Semplifica gli accordi su tre livelli e permette di annullare la modifica.
8. Modifica manualmente testo e timing e li salva dopo il riavvio.
9. Esporta accordi, testo e mix audio.
10. Funziona su desktop e mobile senza layout rotti.
11. I test critici passano: import, analisi, separazione, trasposizione, salvataggio, export.
12. Nessuna funzionalità principale è un mock o un pulsante finto.

## Metodo di lavoro

Procedi in questo ordine:

1. Ispeziona l'ambiente e verifica quali strumenti audio sono disponibili.
2. Scrivi un piano tecnico con rischi, dipendenze e alternative.
3. Crea lo scheletro dell'app, il database e il sistema di job.
4. Implementa prima il flusso con file locali, poi l'adapter YouTube.
5. Implementa analisi, accordi e testi.
6. Implementa separazione stem e mixer.
7. Implementa player, trasposizione, capo e semplificazione.
8. Completa l'interfaccia e l'accessibilità.
9. Aggiungi export, test e documentazione.
10. Esegui una verifica end-to-end e correggi i problemi trovati.

Regole:
- Non fermarti a un MVP se mancano funzionalità richieste.
- Non inventare risultati audio: se una libreria non funziona, dichiaralo e proponi un'alternativa.
- Non chiedere conferma per scelte tecniche reversibili: prendi una decisione motivata e documentala.
- Chiedi conferma solo per azioni distruttive o per un cambio di stack.
- Dopo ogni fase, esegui i test e mostra cosa funziona e cosa manca.
- Mantieni il codice tipizzato, modulare e leggibile.
- Aggiorna il README mentre costruisci, non alla fine.

## Output finale atteso

Consegna:

- repository completo e avviabile;
- `docker-compose.yml`;
- `.env.example`;
- migrazioni del database;
- README con istruzioni;
- test automatici;
- una canzone demo royalty-free;
- elenco delle funzionalità implementate;
- elenco dei limiti noti e delle dipendenze esterne.

Inizia ora con l'ispezione dell'ambiente e il piano tecnico. Poi implementa senza fermarti fino ai criteri di accettazione.