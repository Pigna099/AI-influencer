# Stato installazione — 12 settembre 2026

Cartella server attiva: `/data/data_ssd/pigni/ai-influencer/backend-v3p1` su `192.168.1.60`, utente `john`.

Servizi Docker attivi (progetto `ai-influencer`): API, worker, PostgreSQL. API su `127.0.0.1:8010`, raggiungibile da rete locale su `http://192.168.1.60:8010`; database su `127.0.0.1:55432`.
Configurazione effettiva nel `.env` riservato sul server:
- `TEXT_PROVIDER=ollama`, modello `llama3.1:8b`: collegamento reale verificato.
- `IMAGE_PROVIDER=comfyui`: collegamento reale verificato per foto in chat e immagine profilo.
- `CHAT_IMAGE_ENABLED=true`, `CHAT_IMAGE_NSFW=true`, cooldown 300 s per conversazione.
- Fanvue: non implementato; nessun contenuto viene pubblicato.

## Aggiornamento v3.1 (personalità A/B e hardening)

- Backup pre-deploy in `../backups/v3p1-deploy-20260912/`: dump PostgreSQL, sorgente e `.env` del vecchio servizio.
- Database migrato: era fermo a `0001` ma lo schema corrispondeva alla `0002`; eseguiti `alembic stamp 0002` e `alembic upgrade head`.
- Dati esistenti conservati: 5 personaggi e le chat precedenti; chat e ricordi vecchi assegnati all'Archivio v2 (`fan_id='legacy'`).
- Difese anti-iniezione attive: regole di sicurezza nel prompt, messaggi del fan delimitati in `<fan_message>`, filtro deterministico sull'output per leak verbatim ed eco canary.

## Aggiornamento immagini in chat (12 settembre 2026)

- Migrazione `0004_chat_images` applicata: `influencers.avatar_filename`, `conversations.images_enabled`, tabella `chat_images`.
- Workflow chat: `workflows/chat_default.json`, checkpoint SDXL NSFW `ponyDiffusionV6XL_v6StartWithThisOne.safetensors`, 832×1216, 28 passi, CLIP skip -2. Generazione reale verificata (~9-22 s per foto).
- Immagine profilo: `POST /api/characters/{id}/avatar`, memorizzata sul personaggio e mostrata nella webUI; se il workflow contiene `{{reference_image}}` viene anche caricata su ComfyUI come riferimento.
- Il personaggio decide quando inviare una foto tramite il marcatore `[PHOTO: ...]`; il backend genera l'immagine e la allega al messaggio. Cooldown per conversazione e interruttore **Foto in chat** per singola chat.
- I limiti del personaggio restano vincolanti: un profilo con confini "non espliciti" non invia foto NSFW.
- I negativi contengono sempre `child, minor, teen, underage`: solo adulti.
- Verifiche: 45 test automatici, `ruff check`/`format` puliti, `alembic check` senza modifiche pendenti, build webUI, e verifica reale `scripts/verify_playground.py` con avatar, foto in chat, memoria, injection guard, benchmark `llama3.1:8b` e `qwen3:30b`, variante di personalità, clone ed enhance. Tutte passate.

## ComfyUI sul server

ComfyUI 0.18.1 è installato in `/data/data_ssd/pigni/comfyUI/ComfyUI` (venv interno con PyTorch CUDA, 4× RTX 3090). Al momento della verifica era attivo su `127.0.0.1:8188`. Avvio manuale:

```bash
cd /data/data_ssd/pigni/comfyUI/ComfyUI
setsid nohup ./venv/bin/python main.py --listen 127.0.0.1 --port 8188 \
  > /data/data_ssd/pigni/comfyUI/comfyui.log 2>&1 < /dev/null &
```

Senza ComfyUI attivo la chat resta testuale: il backend verifica la raggiungibilità e non propone foto. La cartella `backend/` (v1) non è più il servizio attivo: eseguire `docker compose` sempre da `backend-v3p1`.

Prossimi passi possibili: aggiungere IPAdapter al workflow chat per usare davvero l'immagine profilo come riferimento di volto, pulsante "invia foto" manuale, e selezione del checkpoint dall'interfaccia.
