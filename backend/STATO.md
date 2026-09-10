# Stato installazione — 9 settembre 2026

Cartella server: `/data/data_ssd/pigni/ai-influencer/backend` su `192.168.1.60`, utente `john`.

Servizi Docker attivi: API, worker, PostgreSQL. API su `127.0.0.1:8010`; database su `127.0.0.1:55432`.
Configurazione effettiva nel `.env` riservato sul server:
- `TEXT_PROVIDER=ollama`, modello `llama3.1:8b`: collegamento reale verificato.
- `IMAGE_PROVIDER=mock`: immagini PNG di prova marcate DEMO.
- Fanvue: non implementato; nessun contenuto viene pubblicato.

Verifiche completate:
- 6 test automatici passati (pipeline/review/versioni, autenticazione/validazione, claim concorrente, errori/recupero, tipi workflow, conservazione tratti e validazione Ollama).
- Ruff: controllo codice e formattazione passati.
- Alembic: database PostgreSQL coerente con i modelli, nessuna modifica di schema pendente.
- Prova completa su Docker/PostgreSQL con provider simulati: passata.
- Prova completa su Docker/PostgreSQL con Ollama reale e immagini simulate: passata.

Sono presenti due personaggi demo creati dalle prove, ciascuno con un contenuto approvato come test tecnico. L'ultimo job è `5e2649ba-8b51-48f9-9bbe-3b5d35becd20`.

Prossimo passo: verificare dove è installato ComfyUI, avviarlo e collegare un workflow API funzionante. Non rispondeva su localhost:8188 al momento dell'ispezione; il suo adapter è presente ma non verificato contro un servizio reale. Vedi `workflows/README.md`.

La copia sul Mac contiene codice e documentazione; il servizio e i dati effettivi sono sul server. Il file `.env` e i media non sono copiati sul Mac.
