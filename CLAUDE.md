# LocalChords — istruzioni per Claude Code

Rispondi sempre in italiano. Quando scrivi percorsi file, usa percorsi completi e copiabili (Windows).

## Cosa stiamo costruendo
App desktop **solo Windows**, local-first, che trasforma un file audio (e opzionalmente un link YouTube) in accordi, testi sincronizzati, tab, diagrammi, 6 stem con mixer e strumenti di pratica.

- Requisiti funzionali completi: `BRIEF_ORIGINALE.md`.
- **Le decisioni in `PIANO.md` prevalgono sul brief** dove differiscono (niente Docker, niente Next.js, niente mobile, niente demo).

## Regole di lavoro
- Segui le fasi di `PIANO.md` in ordine. Dopo ogni fase riporta cosa funziona e cosa manca.
- **Test:** dal 24/11/2026 esistono test eseguibili senza GPU (pytest in `tests/`, con `-m slow` per i modelli veri su CPU; Vitest e Playwright in `frontend/`), su audio sintetico. I test che richiedono CUDA si fanno sul PC con la RTX 3080 Ti. Restano attivi i controlli statici (mypy, ruff, `tsc`) e il build del frontend.
- Non inventare risultati audio. Se un modello o una libreria non funziona, dichiaralo e proponi un'alternativa.
- Scelte tecniche reversibili: decidi, motiva e documenta in `docs/DECISIONI.md`. Chiedi conferma solo per azioni distruttive o cambi di stack.
- Codice tipizzato (mypy/pyright strict, TypeScript strict), modulare e leggibile.
- Aggiorna il `README.md` durante lo sviluppo, non alla fine.
- Ambiente di test: Windows, **RTX 3080 Ti 12 GB**. L'app deve però restare leggera e usabile su PC normali senza GPU (profilo "Leggero").
- Nessun segreto nel repository. Tieni `.env.example` completo.
- Nessun testo protetto e nessuna canzone demo inclusi: l'app parte vuota.
