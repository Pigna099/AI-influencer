# Stato installazione — 13 settembre 2026

## Passaggio a backend-v5p0 (15 settembre 2026)

- Nuova cartella attiva `backend-v5p0/` (copia di `backend-v4p1`); container API/worker ricreati con immagine `ai-influencer-playground:v5p0`, versione app `0.5.0`.
- Snapshot pre-passaggio in `../backups/v4p2/`: dump PostgreSQL, `.env` e sorgente completo.

## Passaggio a backend-v4p1 (13 settembre 2026)

- Nuova cartella attiva `backend-v4p1/` (copia di `backend-v4`); container API/worker ricreati con immagine `ai-influencer-playground:v4p1`, versione app `0.4.1`.
- Snapshot pre-lavori in `../backups/v4p0/`: dump PostgreSQL, `.env` e sorgente completo (esclusi venv e node_modules).
- Inizio della pipeline LoRA per personaggio (Fase A): registry LoRA, coda job di training, trainer kohya-ss sul server.
- Fase A implementata: migrazione `0012_lora_pipeline` (`character_loras`, `lora_datasets`, `lora_dataset_items`, `pose_references`, `training_jobs`), API `/api/loras` e `/api/training-jobs`, scheda **LoRA** (avanzamento live); trainer host in `scripts/trainer/` (venv Python 3.12 + torch cu124 + kohya sd-scripts, worker con coda/GPU libera/heartbeat/recovery). Test: 79 passati.
- Verifica training completata (15 settembre 2026): LoRA `nikita_real_v1` (20 immagini, rank 16, 1000 step, loss finale 0.0738, ~41 min su GPU 1) pronta e attiva; file in `ComfyUI/models/loras/ai_influencer/` e backup in `data/loras/`; generazione di validazione con LoRA riuscita (identità trasferita in una scena nuova). Il worker di training è attivo in background e resiste ai riavvii dell'API.
- Git: `.gitignore` di root aggiunto (`backups/`, `.env`, `node_modules/`, `data/`...). I backup già presenti nella storia remota contengono `.env` datati: ruotare `API_KEY`/`POSTGRES_PASSWORD` per sicurezza.
- Batch 14.7-14.11 (15 settembre 2026): **Human mode** (risposte multiple, refusi con correzione, messaggi spontanei), eliminazione conversazione dalla lista chat, pulsante **Libera VRAM** (unload Ollama + `/free` ComfyUI), fix riclassificazione dataset (ritenta anche le fallite), checkbox dopo il testo nelle UI. Migrazione `0013_human_mode`; 85 test passati.
- Batch 14.12-14.13 (15 settembre 2026): pulsante **Classifica** che forza il riavvio della classificazione dataset (risolto il blocco del dataset `EvaElfie`, ripreso in background con guardia anti-doppio lavoro); generazione della **foto profilo** spostata dalla chat alla scheda **LoRA** (con anteprima e visore). 86 test passati.
- 14.13 est. (15 settembre 2026): pulsanti **Duplica** ed **Elimina** spostati dalla chat alla scheda LoRA; l'eliminazione del personaggio ora pulisce anche LoRA, dataset, job e artefatti in `data/loras` (blocca se un training è in corso). La spec completa della pipeline LoRA è integrata in **PLAN §14.16**. 88 test passati.
- Pipeline LoRA 14.16, prima slice (15 settembre 2026): scaricati **ControlNet OpenPose SDXL** e **DWPose**; estrazione posa via ComfyUI (`POST /api/poses/extract` con guardia "nessuna persona"), **Pose Library** nella scheda LoRA e pulsante **Estrai posa** nel dettaglio immagine del dataset; verificato su un'immagine reale. Checkpoint ridotti a solo PornMaster (110 GB liberati), workflow reali ripuntati su PornMaster. 92 test passati.
- Scheda **Home** + fix scroll (15 settembre 2026): nuova pagina iniziale `/` con flag di stato (API/DB, ComfyUI, Ollama, GPU, trainer), GPU live, personaggi e modelli disponibili; chat spostata su `/chat`, nav aggiornata in tutte le schede; corretto lo scroll della chat (riga di grid vincolata a `minmax(0,1fr)` e overflow contenuto nel pannello).
- Pipeline LoRA 14.16, seconda slice (15 settembre 2026): **generazione dataset con posa** — workflow `chat_real_pose*` (ControlNet OpenPose + IPAdapter), API `/api/datasets` (create/list/detail/generate/patch/delete item) e training **da dataset** (materializzazione automatica con trigger+caption); UI **Dataset** nella scheda LoRA con creazione, generazione candidati, cura e scelta dataset nel training. Verificata una generazione reale identità+posa. 95 test passati.
- Muovi **Libera VRAM** in Home e rimozione pannello GPU dalla chat (15 settembre 2026).
- Riorganizzazione pose/generazione (15 settembre 2026): **Pose Library e selezione posa nella scheda Immagini** (la generazione libreria accetta `pose_ids`/`pose_strength`); la scheda LoRA resta personaggio + dataset + training. Download in background (`scripts/download_models_extra.sh`, riprendibile): LUSTIFY, Qwen-Image base, FLUX.2 (diffusion+text encoder+VAE+turbo LoRA); Qwen-Image-Edit 2509 e Z-Image già presenti. 96 test passati.
- Variazioni **Qwen-Image-Edit** (15 settembre 2026): `POST /api/datasets/{id}/variations` con Qwen-Image-Edit 2509 fp8 + Lightning 4-step; blocco Variazioni nella scheda LoRA → Dataset; validato con generazione reale (stessa identità, scena nuova). Pulizia LoRA ComfyUI non necessarie (~4.3 GB) e ripristino della LoRA 2511 Lightning. 98 test passati.
- Annullamento generazioni, brand **v5** e LoRA a step (15 settembre 2026): `POST /api/images/interrupt` (ComfyUI `/interrupt` + coda) con pulsante Annulla in tutte le UI di generazione (immagini, dataset, foto in chat, avatar); WebUI rinominata **v5**; scheda LoRA riorganizzata in **Personaggio → Dataset → Training** con "+" nuovo personaggio (tolto dalla chat). 99 test passati.
- Analisi dataset e LoRA automatica (15 settembre 2026): `GET /api/datasets/{id}/analysis` (duplicati phash, pose, keyword, avvisi) con barra 20 selezionate nella UI; nella scheda Immagini la LoRA attiva del personaggio si abilita da sola (peso 0.85) quando la famiglia del checkpoint corrisponde. 103 test passati.
- Foto profilo avanzata (15 settembre 2026): scelta del **modello** per la foto profilo, **modifica con Qwen-Image-Edit** (`POST /api/characters/{id}/avatar/edit`) e rigenerazione da zero; "+" personaggio spostato nella barra sinistra della scheda LoRA; hint UI su candidati vs variazioni e sul rank. 102 test passati.
- Multi-LoRA + preset + compatibilità (15 settembre 2026): categorie e CLIP weight per LoRA nel selettore, preset di generazione persistenti (`generation_presets` con migrazione 0014 e UI), filtro che nasconde le LoRA incompatibili con la famiglia del checkpoint. 106 test passati.
- Supporto **Qwen-Image / Z-Image / FLUX.2** (15 settembre 2026): discovery unificata checkpoint+diffusion models, grafi programmatici per famiglia (Qwen-Image 20 step, Z-Image turbo 4 step, FLUX.2 dev + turbo LoRA 8 step con Flux2Scheduler), selettori aggiornati; validati Z-Image (41 s) e FLUX.2 (183 s al primo caricamento). 104 test passati.
- Fix eliminazione (18 settembre 2026): cancellare un'immagine generata dai candidati dava HTTP 500 per violazione di foreign key (immagine eliminata prima dell'item); ora l'item viene rimosso prima dell'immagine e gli anchor vengono azzerati. Aggiunta anche l'eliminazione del dataset (`DELETE /api/datasets/{id}` con immagini e item) e il pulsante nella UI. 109 test passati.
- Import **Instagram** via **Scrapling** (18 settembre 2026): nuova fonte dataset `instagram` (`@profilo` o URL) per riferimenti di posa/stile, cookie opzionali (`INSTAGRAM_COOKIES`), fallback HTTP impersonato (curl-cffi), volume `browser_cache` per l'eventuale modalità stealth. 112 test passati.
- Operativit\`a (18 settembre 2026): `start-ai-influencer.sh` ora avvia anche il **trainer LoRA** host; riavviati in background i download dei modelli video **LTX 2.3** (dev fp8, distilled fp8, distilled LoRA); la Gemma abliterated LoRA del workflow LTX non \`e pi\`u reperibile e va reinserita a mano se serve.
- Generazione **parallela su 4 GPU** (18 settembre 2026): 4 istanze ComfyUI (porte 8188-8191, una per GPU) avviate dallo script di boot; il backend scopre le istanze (`COMFYUI_URLS`), sceglie la meno occupata e lancia i batch (playground, candidati, variazioni) in parallelo. Verifica: 4 immagini SDXL in 71 s (prima ~2-3 min). Interrupt/Libera VRAM ora agiscono su tutte le istanze.
- Scelta del **modello per ogni step del dataset** (18 settembre 2026): selettore modello per le variazioni Qwen-Image-Edit (2509/2511 con pairing automatico della LoRA Lightning) e per i candidati SDXL, con selezione pose (ControlNet) e forza; obiettivo dataset alzato a **40 immagini**; download di **Qwen-Image-2512** fp8 in corso.
- **Guida nella scheda LoRA** (18 settembre 2026): colonna a destra apribile/chiudibile con spiegazione di parametri, checkpoint, prompt, flusso in tre passi e glossario.
- Video: modelli **LTX 2.3** riscaricati (dev fp8 29.1 GB, distilled fp8 29.5 GB, distilled LoRA) — download completato.
- Fix cancellazione training (18 settembre 2026): l'endpoint progress risponde 200 con stato `canceled` (non più 409) e il worker ora termina l'intero process group (`start_new_session` + `killpg` SIGTERM/SIGKILL), quindi il processo kohya non resta orfano sulla GPU; verifica live: cancel rilevato in pochi secondi, VRAM liberata, worker pronto per il job successivo. Nota: con `CUDA_VISIBLE_DEVICES=3` i log CUDA interni mostrano "GPU 0" (rinumerazione), la selezione GPU era corretta. Il progress ignora ora la barra di cache latents.
- Fix OOM training LoRA (18 settembre 2026): il worker trainer ora richiede ~16 GB liberi sulla GPU migliore, se necessario scarica i modelli dalle istanze ComfyUI via `/free` (verificato: 21,5 GB -> 1,2 GB usati) e in caso di CUDA OOM ritenta una volta su un'altra GPU; aggiunto `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Job **nikitaV1** riaccodato: training su GPU 0 (40 immagini, 4000 step, rank 32, ETA ~3,5 h), il LoRA viene pubblicato e attivato automaticamente al termine.
- Playground v2.5 selezionabile per i candidati (18 settembre 2026): aggiunto alla lista SDXL del passo candidati; il grafo playground ora supporta **IPAdapter** (Easy-Use, preset PLUS) per il riferimento identità e **ControlNet OpenPose** per la posa, come il ramo SDXL. Verificato live (candidato full-body con posa e identità asiatica preservata). 118 test passati.
- Selezione multipla ed eliminazione in blocco (18 settembre 2026): checkbox con "Seleziona tutte" e "Elimina selezionate (N)" (con conferma) nella griglia foto del dataset (scheda LoRA) e nella libreria della scheda Immagini; endpoint `POST /api/loras/dataset-items/bulk-delete` e `POST /api/library/bulk-delete` (puliscono anche riferimenti e voci dataset collegate). 118 test passati.
- Fix "Amplia con un modello installato" (18 settembre 2026): nella scheda LoRA il form nuovo personaggio riceveva una lista modelli vuota, quindi il menu era vuoto; ora `CharacterForm` carica da sé i modelli chat Ollama quando la lista non è passata dal genitore e sincronizza la selezione quando arrivano.
- Fix generazione identità (18 settembre 2026): nella scheda dataset la famiglia veniva presa dal dataset (`real`) anche scegliendo un modello Qwen/Z-Image/FLUX/Playground, causando `400 value_not_in_list` sul workflow SDXL; ora la famiglia segue il checkpoint scelto. Inoltre gli errori di rifiuto del workflow mostrano il dettaglio dei `node_errors` e si ritenta su un'altra istanza ComfyUI. Predisposti **prompt identità** e **20 scene** di default (con "Ripristina default"); nuova sezione richiudibile **Prompt del personaggio** nello step 1: mostra/salva la parte identità del prompt della foto profilo (soggetto + aspetto) e la include nei candidati identità, così etnia e tratti non si perdono nelle fasi successive. 117 test passati.
- Checkpoint **Playground v2.5** (18 settembre 2026): scaricato `playground-v2.5-1024px-aesthetic.fp16.safetensors` (6.9 GB) per foto quotidiane realistiche e non esplicite; famiglia `playground` con grafo dedicato (ModelSamplingContinuousEDM, dpmpp_2m/sgm_uniform, 30 step, cfg 3) e supporto LoRA SDXL del personaggio. Verificata una generazione reale con LoRA (21 s).
- **Pipeline dataset a reference canoniche** (18 settembre 2026): nuovo flusso in tre fasi — (1) 20-50 candidati identità con Qwen-Image-2512, (2) cura manuale e scelta di 4-8 **reference canoniche** con ruoli (volto ravvicinato, 3/4, profilo, mezzo busto, figura intera frontale/3-4/laterale), (3) due **rami indipendenti** (variazioni Qwen-Image-Edit e candidati SDXL+IPAdapter+ControlNet posa) che confluiscono nella stessa griglia di cura. Migrazione `0015_dataset_references` (ruolo sui dataset item); l'analisi segnala poche reference; obiettivo portato a **60** immagini finali (50-70). Qwen-Image-2512 fp8 scaricato (19 GB) e selezionabile.

## Passaggio a backend-v4

- Nuova cartella attiva `backend-v4/` (copia di `backend-v3p3` con stessi dati e volume PostgreSQL); container API/worker ricreati con immagine `ai-influencer-playground:v4`.
- Backup pre-switch in `../backups/v4-start-20260913/` (dump database + `.env`).
- WebUI e API ora v4 (`0.4.0`); la cartella `backend-v3p3/` resta come versione precedente.
- Verifiche post-switch: 65 test, ruff/format puliti, health ok, 3 personaggi e media intatti.

Cartella server attiva: `/data/data_ssd/pigni/ai-influencer/backend-v5p0` su `192.168.1.60`, utente `john`.

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

- Interfaccia bilingue italiano/inglese con selettore **IT · EN** (barra in alto e login); la scelta è salvata nel browser e gli errori API vengono tradotti tramite l'header `X-Language` (`app/i18n.py`). Lingua dei personaggi indipendente da quella dell'interfaccia.

- `GET /api/system/gpus` (NVML dentro il container, `gpus: all` + `pid: host` nel compose) con memoria, utilizzo, potenza e temperatura delle 4× RTX 3090, più processi per GPU. I runner Ollama vengono associati ai modelli caricati tramite `/api/ps` e mostrati con il nome e i GB per GPU; ComfyUI è etichettato a parte.
- La webUI aggiorna il pannello GPU ogni 3 secondi.
- Clic su immagine profilo o su una foto in chat: apertura a schermo intero (chiusura con clic o Esc).
- Barra dei comandi della chat compattata: azioni rapide (Apri, Ritorno, Invia foto, Auto foto) e menu **Opzioni** per assenza, intervento automatico ed eliminazione chat; spazi verticali ridotti per dare più spazio ai messaggi.
- Verifiche: 48 test automatici, ruff/format puliti, build webUI, endpoint GPU reale con i 4 modelli su 4 GPU e ComfyUI su GPU0.

## Modelli immagine e Pony (13 settembre 2026)

- Nuovo checkpoint scaricato: `CyberRealisticPony_V18.0_F16.safetensors` (autore, FP16, 6.94 GB) accanto a `lustifySDXLNSFWSFW_v20.safetensors` e `NoobAI-XL-v1.1.safetensors`.
- Script riprendibile e parallelo `scripts/download_models.py` (CyberRealistic Pony e LUSTIFY da HuggingFace; PornMaster Pro dalla fonte Civitai con `--civitai-model-id` e `CIVITAI_TOKEN`, senza scraping).
- Rilevamento automatico della famiglia dal checkpoint: `pony` → workflow `chat_pony*.json` con score tag Pony, Euler a, 28 passi, CFG 6.5, CLIP skip -2; altrimenti Anime/Reale. Prompt, negativi e workflow si adattano da soli.
- Interfaccia: il menu **Checkpoint foto** mostra la famiglia accanto al nome.
- Verifica reale: generazione con CyberRealistic Pony (mirror selfie fotorealistico, prompt con score tag, 2.5 MB) e famiglia `pony` nei metadati. 60 test automatici, ruff/format puliti.
- PornMaster-Pro SDXL scaricato da Civitai con il token dell'utente (autore `iamddtla`, model `1031308`, versione `1167499`): `pornmasterProSDXL_sdxlV2VAE_1072864.safetensors` (6.94 GB, FP16). Generazione reale verificata (foto fotorealistica). Il token è salvato solo nel `.env` privato; lo script ora preferisce i file FP16 e supporta `--civitai-version-id`/`--civitai-file`.
- Filtro checkpoint esteso: i modelli non compatibili con i workflow SDXL (Flux, SD1.5, Qwen, ecc.) sono `unsupported` e nascosti dal selettore, oltre ai video.
- Richieste future registrate in `../PLAN.md` §14 senza implementazione: pagamenti simulati/PPV con immagini bloccate, notifiche e ritardi casuali, playground video, filtro modelli, temi colore, flusso personaggio→dataset→LoRA.

## Risposte realistiche (13 settembre 2026)

- Migrazione `0011_reply_scheduling`: ritardi/orari su `influencers`, `conversations.last_read_at`, tabella `scheduled_replies`.
- Scheduler interno all'API (lifespan) con poll ogni 3 s; coda persistente con `deliver_at`, tentativi e retry su conversazione occupata.
- Verifica reale: `deliver_at` spostato alle 09:00 del giorno dopo con orari 9–18 attivi di sera; risposta 5–10 s consegnata in 26 s; non letti 1 → 0 con segna-come-letto; ritardo 0 → risposta immediata. 68 test, ruff/format e `alembic check` puliti.

## PPV, filtro modelli, temi (13 settembre 2026)

- Migrazione `0009_ppv`: `influencers.ppv_enabled/ppv_price_cents`, `chat_images.price_cents/unlocked_at`, tabella `simulated_payments`.
- PPV simulato: marcatore `[PPV:]`, anteprima sfocata lato backend, endpoint di sblocco con pagamento finto registrato, toggle e prezzo per personaggio, invio manuale bloccato. I test coprono blocco, blur, sblocco e declassamento a foto gratuita.
- Filtro modelli: `kind` chat/coding/embedding per Ollama; checkpoint con `{name, family, usable}` (Video esclusi dal selettore).
- Temi: accenti diversi per Chat/Immagini/Dataset via variabili CSS.
- Verifica reale: import Telegram da 120 elementi (85 immagini + 35 video, oltre il vecchio tetto di 100), video servito `video/mp4` con anteprima JPEG; PPV bloccato/sbloccato con pagamento simulato; filtri modelli/checkpoint attivi. 65 test automatici, ruff/format puliti, `alembic check` pulito.

## Dataset immagini (13 settembre 2026)

- Migrazione `0008_dataset`: tabelle `dataset_sources` e `dataset_images`; file in `data/dataset/<source_id>/`, cartella import `data/imports/` (volume Docker `./data:/app/data`).
- Fonti: canale Telegram pubblico (`t.me/s/...`, paginazione `before`, fino a 2000 elementi), URL immagini, cartelle sotto `data/imports` (immagini e video). Instagram non viene scrapato (ToS Meta + vincolo no-likeness): si usa export/URL propri.
- I video Telegram vengono scaricati e marcati `kind=video` con anteprima; l'AI descrive solo le immagini (pose/scena dai video in un passo futuro). Filtro `kind` sulla lista immagini e endpoint `/thumb` dedicato.
- Descrizione ricca con `gemma3:27b`: caption + posa, ambiente, luce, scena, outfit, corpo, pelle, inquadratura, mood, stile, tag; flag `minor_apparent` che blocca l'immagine se true.
- UI **Dataset** (terza scheda): import con avanzamento, griglia immagini, dettagli per immagine, classifica in attesa, export JSONL e **Genera profilo** con creazione del personaggio dalla bozza.
- Pannello destro del playground immagini ora **ridimensionabile** (280–700 px, larghezza salvata nel browser).
- Verifica reale eseguita: import di 2 foto da URL + descrizione strutturata, import di 2 immagini da canale Telegram pubblico, export JSONL (2 righe) e sintesi profilo da parte dell'LLM. Passata. 59 test automatici, ruff/format puliti, `alembic check` senza modifiche pendenti.

## Playground immagini e libreria (13 settembre 2026)

- Doppia interfaccia: **Chat** e **Immagini** (link nella barra in alto). Migrazione `0007_image_library` con tabella `image_library` per personaggio.
- Generazione batch (1–4) dal playground con stile, checkpoint, **LoRA** (catena `LoraLoader` inserita dal backend), prompt aumentabile con l'LLM, classificazione vision (`gemma3:27b` → didascalia + tag) ed embedding (`nomic-embed-text`).
- Cura: approva/scarta/valuta (1–5)/elimina/classifica; le approvate sono le uniche usabili in chat.
- Riuso in chat: se esiste un'immagine approvata abbastanza simile (embedding + tag, soglia 0.55) viene inviata senza generare; altrimenti si genera e si salva una bozza (origine chat) per la cura. Contatore d'uso per immagine.
- Verifica reale eseguita: generazione di 2 foto con caption/tag AI, approvazione, invio manuale dalla libreria con contatore, e match diretto dell'embedding sull'immagine approvata. Passata. 57 test automatici, ruff/format puliti, `alembic check` senza modifiche pendenti.

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

Senza ComfyUI attivo la chat resta testuale: il backend verifica la raggiungibilità e non propone foto. La cartella `backend/` (v1) non è più il servizio attivo: eseguire `docker compose` sempre da `backend-v5p0`.

Prossimi passi possibili: invio foto programmato (campagne), più immagini per messaggio, controllo di similarità del volto per scartare le foto fuori personaggio, e pubblicazione verso Fanvue (oggi solo segnaposto).
