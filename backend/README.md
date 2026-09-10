# Backend AI Influencer — prima versione

Questa è la parte del progetto che gestisce personaggi e richieste di contenuti. La futura interfaccia web chiamerà queste API. Per ora `/docs` offre una pagina tecnica interattiva per provarle.

## Che cosa fa

- Salva influencer e descrizione del personaggio (character bible), mantenendo le versioni precedenti.
- Riceve richieste di contenuti e le salva in una coda persistente nel database.
- Un **worker**, cioè un processo separato, prende un lavoro alla volta e genera il brief e le immagini.
- Ollama genera caption e prompt in JSON validato; ComfyUI esegue un workflow configurato.
- Conserva immagini sull'SSD, hash e metadati nel database.
- Consente approvazione, scarto e rigenerazione, conservando la cronologia.
- Modalità `mock`: crea testi e immagini chiaramente marcati DEMO, senza usare la GPU.

**Fanvue non è ancora collegato.** Approvare un contenuto lo marca come approvato nel database; non lo pubblica. Il modulo `app/integrations/fanvue.py` è solo il punto predisposto per una futura integrazione.

## Componenti e scelta iniziale

Python + FastAPI per l'API, SQLAlchemy per il database, Alembic per aggiornare la sua struttura, PostgreSQL in Docker e un worker Python. La coda è nel database: non richiede Redis/Celery. I file sono nell'SSD: non richiedono MinIO. Sono semplificazioni intenzionali per la prima installazione. SQLite è disponibile per test/sviluppo locale; Docker usa PostgreSQL.

## Avvio sul server con Docker

Dalla cartella `/data/data_ssd/pigni/ai-influencer/backend`:

```bash
# Solo alla prima configurazione, se .env non esiste:
cp .env.example .env
# Inserire chiavi casuali in API_KEY e POSTGRES_PASSWORD (password PostgreSQL esadecimale).
mkdir -p data/media
# Sul server attuale l'utente john ha UID 1000, come l'utente del container.
docker compose up -d --build
# Stato e log:
docker compose ps
docker compose logs --tail=60 worker
```

L'API ascolta solo sul server, su `127.0.0.1:8010`. PostgreSQL ascolta su `127.0.0.1:55432`. Il file `.env` contiene segreti, è escluso da Git e non va condiviso. `DATABASE_URL` nel Compose sostituisce quello del file `.env` per usare PostgreSQL.

## Aprire dal Mac / VS Code

In VS Code con Remote SSH, collegati a `192.168.1.60` e apri `/data/data_ssd/pigni/ai-influencer`. Nel pannello **Ports/Porte**, inoltra la porta **8010**. In alternativa, dal terminale del Mac:

```bash
ssh -N -L 8010:127.0.0.1:8010 192.168.1.60
```

Lascia quel terminale aperto e visita http://localhost:8010/docs. Clicca **Authorize** e inserisci il valore `API_KEY` del file `.env` sul server.

Per provare dalla pagina:

1. `POST /influencers` → Try it out → crea un personaggio. Copia il suo `id`.
2. `POST /content-jobs` → inserisci quell'ID in `influencer_id`, scegli `theme` e `image_count` (1–4).
3. `GET /content-jobs/{job_id}` → controlla il lavoro; quando è `awaiting_review`, trovi gli asset e il brief.
4. `GET /assets/{asset_id}/file` → scarica l'immagine.
5. `POST /content-jobs/{job_id}/review` → scegli `approved` o `rejected`.

Esempio personaggio:

```json
{"name":"Demo","bible":{"description":"Personaggio anime adulto, artista di 25 anni, occhi verdi","style":"anime","tone_of_voice":"cordiale","boundaries":"","lora_token":""}}
```

Esempio richiesta:

```json
{"influencer_id":"ID_COPIATO","theme":"Passeggiata al parco","outfit":"giacca azzurra","scenario":"primavera","image_count":1,"seed":42}
```

## Collegare i modelli reali

Per Ollama: `TEXT_PROVIDER=ollama`, `OLLAMA_MODEL=llama3.1:8b`. Per ComfyUI seguire `workflows/README.md` e impostare `IMAGE_PROVIDER=comfyui`. Dopo modifiche a `.env`:

```bash
docker compose up -d --force-recreate api worker
```

Il Compose usa la rete host del server Linux affinché i container possano raggiungere i servizi locali. Non avvia né modifica Ollama o ComfyUI. È possibile usare testo reale e immagini simulate separatamente.

## Test e sviluppo senza Docker

```bash
uv sync --locked
mkdir -p data/media
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
# In un secondo terminale:
uv run python -m app.worker
# Test isolati, non toccano i dati veri:
uv run pytest -q
# Prova sull'API in esecuzione, crea dati demo:
uv run python scripts/smoke.py
```

Non avviare contemporaneamente l'API locale e Docker sulla stessa porta. Per lo smoke test del servizio Docker usare `docker compose exec -T api python scripts/smoke.py`.

## Gestione quotidiana

- Fermare: `docker compose stop`; riavviare: `docker compose up -d`.
- I dati restano nel volume PostgreSQL e in `data/media`. Non usare `docker compose down -v`: eliminerebbe il database.
- Backup: salvare insieme dump PostgreSQL (`docker compose exec -T db pg_dump -U influencer influencer > backup.sql`), `data/media`, `workflows` e `.env` in luogo riservato. Per coerenza fermare API e worker durante il backup e riavviarli dopo.
- Un lavoro interrotto rimane `running` fino alla scadenza della finestra di 20 minuti e poi passa a `failed`. Non viene ritentato automaticamente, per evitare generazioni duplicate. Controlla ComfyUI prima di rigenerare.
- La rigenerazione crea un nuovo lavoro con la stessa descrizione del personaggio, seed incrementato e i provider configurati al momento dell'esecuzione. Per usare una bible aggiornata, crea una nuova richiesta.

## Limiti attuali

Un solo worker previsto, immagini soltanto, nessun calendario o login multiutente. Nessuna pubblicazione Fanvue, gestione LoRA o distribuzione su più GPU. Il workflow deve essere esportato e validato dall'installazione ComfyUI reale. La chiave API condivisa è adatta a questo uso interno tramite tunnel SSH; prima di un accesso pubblico servirà autenticazione utente.

I job sopravvivono ai riavvii. Un arresto esattamente durante il salvataggio può lasciare file non referenziati da pulire; non è ancora presente uno strumento di riconciliazione. Non c'è annullamento di una generazione già inviata a ComfyUI.

Riferimenti usati per gli adapter: https://docs.ollama.com/api/chat e https://docs.comfy.org/development/comfyui-server/comms_routes.
