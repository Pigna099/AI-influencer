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

- Migrazioni applicate: `0004_chat_images` (`influencers.avatar_filename`, `conversations.images_enabled`, tabella `chat_images`) e `0005_image_checkpoint` (`influencers.image_checkpoint`).
- Workflow chat: `workflows/chat_default.json`, checkpoint SDXL NSFW `ponyDiffusionV6XL_v6StartWithThisOne.safetensors`, 832×1216, 28 passi, CLIP skip -2. Generazione reale verificata (~9-22 s per foto).
- Riferimento di volto: `workflows/chat_reference.json` con `easy ipadapterApplyADV` (IPAdapter Plus). Installato `ComfyUI_IPAdapter_plus` in `custom_nodes/`; i modelli `ip-adapter-plus_sdxl_vit-h.safetensors` e `clip-vit-h-14-laion2B-s32B-b79K.safetensors` sono in `models/ipadapter/` (scaricati automaticamente da Easy-Use). Con un'immagine profilo presente, le foto usano il workflow con riferimento; senza immagine si torna al workflow semplice.
- Immagine profilo: `POST /api/characters/{id}/avatar`, memorizzata sul personaggio e mostrata nella webUI; in rigenerazione usa la foto precedente come riferimento.
- Il personaggio decide quando inviare una foto tramite il marcatore `[PHOTO: ...]`; il backend genera l'immagine e la allega al messaggio. Cooldown per conversazione e interruttore **Foto in chat** per singola chat.
- Invio manuale: `POST /api/conversations/{id}/photo` con scena e didascalia; pulsante **Invia foto** nella webUI. Ignora cooldown e interruttore automatico, richiede ComfyUI attivo.
- Checkpoint per personaggio: `GET /api/images/checkpoints` elenca i checkpoint installati, `PUT /api/characters/{id}/image-checkpoint` salva la scelta; menu **Checkpoint foto** nella colonna del personaggio.
- I limiti del personaggio restano vincolanti: un profilo con confini "non espliciti" non invia foto NSFW.
- I negativi contengono sempre `child, minor, teen, underage`: solo adulti.
- Verifiche: 48 test automatici, `ruff check`/`format` puliti, `alembic check` senza modifiche pendenti, build webUI, e verifica reale `scripts/verify_playground.py` con avatar, foto in chat (con riferimento IPAdapter), memoria, injection guard, benchmark `llama3.1:8b` e `qwen3:30b`, variante di personalità, clone ed enhance. Tutte passate.

## Monitoraggio GPU e interfaccia (12 settembre 2026)

- `GET /api/system/gpus` (NVML dentro il container, `gpus: all` + `pid: host` nel compose) con memoria, utilizzo, potenza e temperatura delle 4× RTX 3090, più processi per GPU. I runner Ollama vengono associati ai modelli caricati tramite `/api/ps` e mostrati con il nome e i GB per GPU; ComfyUI è etichettato a parte.
- La webUI aggiorna il pannello GPU ogni 3 secondi.
- Clic su immagine profilo o su una foto in chat: apertura a schermo intero (chiusura con clic o Esc).
- Barra dei comandi della chat compattata: azioni rapide (Apri, Ritorno, Invia foto, Auto foto) e menu **Opzioni** per assenza, intervento automatico ed eliminazione chat; spazi verticali ridotti per dare più spazio ai messaggi.
- Verifiche: 48 test automatici, ruff/format puliti, build webUI, endpoint GPU reale con i 4 modelli su 4 GPU e ComfyUI su GPU0.

## Tuning delle immagini (12 settembre 2026)

- Due stili selezionabili per personaggio (**Stile foto**): **Reale** con `lustifySDXLNSFWSFW_v20.safetensors` (LUSTIFY v2, fotorealistico NSFW) e **Anime** con `NoobAI-XL-v1.1.safetensors` (Illustrious NSFW). Entrambi scaricati in `models/checkpoints/`.
- Quattro workflow: `chat_real.json`, `chat_real_reference.json`, `chat_anime.json`, `chat_anime_reference.json`. Ogni workflow ha hires fix 832×1216 → 1216×1824 e FaceDetailer per volto (`face_yolov8m`) e mani (`hand_yolov8s`).
- IPAdapter tarato: weight 0.6 (reale) / 0.5 (anime), `embeds_scaling: K+V`. Con `V only` o weight 0.8 il modello anime produceva artefatti.
- Traduzione automatica delle scene in inglese con `IMAGE_PROMPT_MODEL=mistral-small3.2:latest`: `llama3.1:8b` rifiutava di tradurre scene esplicite. In caso di rifiuto si mantiene il testo originale.
- Verifica visiva con generazioni reali: reale fotorealistico con volto e pelle buoni, anime pulito senza artefatti; i tempi sono circa 40–50 s per foto completa di hires e detailer.
- Nota: le immagini anime possono risultare morbide; si può regolare `weight`, passi e denoise nei JSON. Il modello di traduzione è configurabile in `.env`.

## ComfyUI sul server

ComfyUI 0.18.1 è installato in `/data/data_ssd/pigni/comfyUI/ComfyUI` (venv interno con PyTorch CUDA, 4× RTX 3090). Al momento della verifica era attivo su `127.0.0.1:8188`. Avvio manuale:

```bash
cd /data/data_ssd/pigni/comfyUI/ComfyUI
setsid nohup ./venv/bin/python main.py --listen 127.0.0.1 --port 8188 \
  > /data/data_ssd/pigni/comfyUI/comfyui.log 2>&1 < /dev/null &
```

Senza ComfyUI attivo la chat resta testuale: il backend verifica la raggiungibilità e non propone foto. La cartella `backend/` (v1) non è più il servizio attivo: eseguire `docker compose` sempre da `backend-v3p1`.

Prossimi passi possibili: invio foto programmato (campagne), più immagini per messaggio, controllo di similarità del volto per scartare le foto fuori personaggio, e pubblicazione verso Fanvue (oggi solo segnaposto).
