# PLAN — Da playground a influencer autonoma

Piano di lavoro per trasformare il playground (`backend-v5p0`) in una piattaforma che genera contenuti, pubblica su Instagram e gestisce i fan su Fanvue con vendita di foto/video.

Documento vivo: aggiornare quando una decisione cambia.

## 1. Obiettivo

- Generare contenuti (foto e video) coerenti per uno o più personaggi AI.
- Pubblicare in automatico su Instagram.
- Gestire conversazioni e vendite su Fanvue.
- Aumentare l'autonomia in modo graduale, con controllo umano dove serve.

Vincolo di identità: **personaggi completamente sintetici**, nessuna likeness di persone reali. Un link a un profilo Instagram pubblico è solo un riferimento di stile/pose, non un volto da replicare.

## 2. Decisioni prese

| Tema | Decisione |
|---|---|
| Playground | Resta sandbox interna. Non si fonde col prodotto. |
| Identità personaggio | Sintetica, fissata con **LoRA dedicata per personaggio**. |
| Reference IG | Solo moodboard/stile: pose, outfit, luce, composizione, cadenza, tono caption. |
| Modelli base | SDXL-family (Pony/Illustrious) come cavallo di battaglia; Flux fp8/GGUF per gli shot hero. |
| Video | i2v da immagine già approvata (Wan 2.x / LTX-Video / HunyuanVideo / SVD). |
| Local vs cloud | Locale di default; cloud solo per burst, training lunghi o modelli oltre i 24GB. Routing nell'orchestratore. |
| Autonomia | Human-in-the-loop iniziale, autonomia crescente guidata dai dati. |
| Deployment | Server GPU = generazione. Publisher/scheduler/chat su VPS separato. |
| Compliance | Disclosure AI, niente likeness reale, solo adulti, moderazione, audit. |

## 3. Cosa è riusabile oggi

| Componente | File (backend-v5p0) | Riuso |
|---|---|---|
| Client ComfyUI (parameterize, checkpoint, upload reference/IPAdapter) | `app/integrations/comfyui.py` | Alto — base del workflow selector |
| Client Ollama (chat, embed, metrics) | `app/integrations/ollama.py` | Alto |
| Prompt/injection guard, memoria, estrazione | `app/chat_service.py` | Alto — motore del chatbot fan |
| Modelli `Influencer/Fan/Conversation/Memory/ChatImage` | `app/db.py` | Medio — da estendere |
| Job + worker (DB queue) | `app/main.py`, `app/worker.py` | Medio — pattern corretto, da irrobustire |
| Adapter Fanvue | `app/integrations/fanvue.py` | Da scrivere (API Fanvue esiste, vedi §9) |
| WebUI playground | `webui/` | No come prodotto: resta sandbox |
| Pipeline legacy `/content-jobs` | `app/main.py` | Bassa |

Azione: estrarre le parti riusabili in un package `core/` condiviso (`comfyui`, `ollama`, `chat_service`) e costruire i servizi di prodotto sopra.

## 4. Architettura target

```
[VPS economico]                              [Server GPU 4x3090, dietro WireGuard/Tailscale]
 orchestratore / API  <---- job queue ---->   gpu-worker (poll)
 scheduler (cron/beat)                        |- ComfyUI (1 processo per GPU)
 publisher (IG, Fanvue)                       |- trainer LoRA (kohya / diffusion-pipe)
 chat-agent (fan)                             |- video i2v + TTS + lipsync
 PostgreSQL + Redis + MinIO/S3                |- face-QC / tagger / upscaler
```

Regole:
- Il server GPU non è mai esposto: solo il worker esce in polling.
- Publisher/chat/scheduler sul VPS: la pubblicazione non dipende dall'uptime dei 3090.
- Media su object storage (MinIO/S3), non su disco locale: l'API Instagram fa il cURL del file, l'URL deve essere pubblico.
- Coda: partire dalla tabella `jobs`, poi Redis + RQ/Celery per scheduling e autonomia.
- CPU (Xeon E5-2650v4) è il collo di bottiglia per ffmpeg e prep del dataset: tenere i file su NVMe.
- Assegnare le GPU per ruolo (es. GPU0 ComfyUI, GPU1 training, GPU2/3 video/Ollama) per evitare contesa.

## 5. Dati (estensioni al database)

Oltre ai modelli attuali (`Influencer`, `Fan`, `Conversation`, `Memory`, `ChatImage`) servono:

- `CharacterLora` — versione LoRA, base checkpoint, trigger word, stato training, metrica.
- `ReferenceSet` — moodboard di input e metadati di stile estratti (Character DNA).
- `ContentItem` — bozza/contenuto generato (tipo, prompt, provider, workflow, stato, QC).
- `AssetVersion` — varianti di un contenuto, similarità volto, classificazione.
- `Approval` — decisione umana su contenuto/messaggio, note, attore, timestamp.
- `Schedule` / `Post` — pianificazione, piattaforma, stato pubblicazione, id esterni, disclosure.
- `SocialAccount` — credenziali/token (IG, Fanvue), scope, scadenza, refresh.
- `FanMessageDraft` — bozza risposta, stato approvazione, invio.
- `Pricing` / `Offer` — prezzo PPV, regole promozionali.
- `AuditEvent` — log immutabile di ogni pubblicazione/invio/decisione.
- `CostEntry` — costo per job/personaggio/provider.

## 6. Personaggio: reference -> DNA -> LoRA

1. Moodboard manuale (niente scraping automatico: viola i ToS e rischia la likeness).
2. Auto-tagging/VLM (Florence-2, WD14): pose, outfit, luce, composizione, palette.
3. `Character DNA`: attributi fisici sintetici, pillar di contenuto, libreria pose, voce per le caption.
4. Generazione reference identitarie (base SDXL + IPAdapter dal seed scelto) e curatela.
5. Captioning + trigger word per personaggio.
6. Training LoRA (kohya_ss / diffusion-pipe); SDXL comodo in 24GB, Flux fp8/GGUF al limite.
7. QC automatico con InsightFace/ArcFace per scartare asset fuori personaggio.
8. La LoRA è legata al base checkpoint: una LoRA SDXL non è portabile senza test.

## 7. Workflow ComfyUI: registry e routing

- Workflow come JSON template versionati, con i placeholder già in uso (`{{positive_prompt}}`, `{{negative_prompt}}`, `{{seed}}`, `{{image_count}}`, `{{reference_image}}`).
- Chiave di registry: `(content_type, model_family, has_reference, lora)`.
- L'orchestratore seleziona con regole, non l'utente:
  - `photo_feed` -> SDXL/Pony + LoRA personaggio
  - `hero_shot` -> Flux fp8/GGUF
  - `reel_i2v` -> Wan/LTX da immagine approvata
- Checkpoint e LoRA sono proprietà del personaggio; il workflow è regola di sistema con override espliciti.
- Multi-GPU: 4 istanze ComfyUI su porte 8188-8191 con `CUDA_VISIBLE_DEVICES`, dispatcher che bilancia; oppure job tipo "device" già assegnato.

## 8. Instagram

- Via ufficiale: **Instagram Graph API Content Publishing**. Niente browser automation (ban).
- Requisiti: account IG Business/Creator + Pagina FB collegata + Meta App con `instagram_business_content_publish` (o `instagram_content_publish`) + App Review. Un token per account/personaggio.
- Limiti: ~50-100 post/24h, no Stories via API, scheduling non nativo (coda + cron).
- Il media deve essere su URL pubblico al momento del publish.
- Disclosure AI obbligatoria: `is_ai_generated=true` alla creazione del container (solo sul container padre nei caroselli).
- DM Instagram limitati (API user-initiated): l'interazione commerciale si sposta su Fanvue.

## 9. Fanvue

API OAuth 2.0 (nessuna API key; Bearer token con scope, access token ~1h con refresh). Endpoint rilevanti:

- Chat: `GET /chats?filter=unread`, `GET /chats/{userUuid}/messages`, `POST /chats/{userUuid}/message`.
- Mass messaging con liste (subscribers, expired, spent_more_than_50, ecc.) e `scheduledAt`.
- Post programmati con `publishAt`, prezzo PPV (`price`, min. 300 cent), media.
- Automated messages su trigger (new_subscriber, renewed, first_message_reply, ...).
- Upload media e insights.

Il `chat_service` esistente genera le bozze; `fanvue.py` diventa l'adapter OAuth con refresh e storage sicuro dei token per creator.

## 10. Autonomia

- Macchina a stati con gate di approvazione.
- Livelli: bozza -> approvata -> pubblicata, con escalation all'umano su incertezza o rischio.
- QC automatico (volto, NSFW/adult-only, similarity) come pre-condizione alla pubblicazione.
- Autonomia piena solo per categorie a basso rischio e dopo metriche che la giustificano.
- Kill switch per personaggio/piattaforma.

## 11. Compliance

- Disclosure AI su Instagram (`is_ai_generated`) e su Fanvue.
- Age verification delegata alla piattaforma; contenuti solo adulti (i negativi attuali con `child, minor, teen, underage` restano).
- Moderazione chat; nessuna likeness di persone reali.
- Audit log di pubblicazioni, invii e decisioni.
- Verificare le policy aggiornate di Meta e Fanvue prima del go-live.

## 12. Roadmap

### Fase 0 — Fondamenta
- Estrarre `core/`; object storage (MinIO/S3); coda; registry workflow/modelli; migrazioni per i nuovi modelli DB; audit e cost tracking base.
- Deliverable: playground intatto + struttura servizi condivisa.

### Fase 1 — Personaggi
- Moodboard -> Character DNA -> LoRA per personaggio + QC volto.
- Deliverable: creazione personaggio riproducibile con coerenza misurata.

### Fase 2 — Contenuti
- Pipeline foto/video con bozza, approvazione umana, content bank, caption.
- Deliverable: contenuti approvabili e archiviati.

### Fase 3 — Instagram
- Publisher Graph API, scheduler, disclosure, rate limiting, media pubblico.
- Deliverable: pubblicazione automatica con approvazione.

### Fase 4 — Fanvue
- Adapter OAuth, chat-agent in bozza, mass message e post PPV programmati, automated messages.
- Deliverable: gestione fan e vendita con controllo umano.

### Fase 5 — Autonomia
- Loop analytics -> prompt/pricing; autonomia crescente; kill switch.
- Deliverable: operatività semi-autonoma misurata.

### Trasversale
- Compliance, osservabilità, backup, controllo costi.

## 13. Rischi

| Rischio | Mitigazione |
|---|---|
| Instagram: ToS/ban | Solo Graph API ufficiale; niente automazione browser |
| Likeness persone reali | Solo identità sintetiche; reference solo di stile |
| LoRA incoerente | QC volto (ArcFace) come gate prima della pubblicazione |
| Server GPU esposto | Solo worker in polling, dietro WireGuard/Tailscale |
| Publisher dipende dal server GPU | Publisher e scheduler sul VPS |
| Costi cloud fuori controllo | Budget e limiti nel router local/cloud |
| Contesa GPU | Assegnazione GPU per ruolo, code separate |

## 14. Backlog prodotto richiesto (NON in esecuzione)

Queste voci sono richieste esplicite, da pianificare e implementare in passi successivi. Non sono ancora state realizzate.

### 14.1 Pagamenti simulati e PPV — FATTO (13 settembre 2026)

- Metodo di pagamento fittizio per simulare transazioni dentro la chat (nessun processore reale).
- Il personaggio può inviare immagini **bloccate/sfocate**; il fan "paga" per sbloccarle.
- Modello dati: `Payment`/`Unlock` (importo, stato simulato, riferimento immagine/messaggio, timestamp) + prezzo per immagine nella libreria.
- UI: badge "locked" sull'immagine, pulsante "Sblocca (simulato)" con conferma, effetto blur lato client, traccia nella chat e nelle metriche.
- Vincoli: nessun dato di pagamento reale, nessuna integrazione con circuiti; solo simulazione per testare tono, prezzo e flusso.
- Implementato: colonne PPV su personaggio e chat, marcatore `[PPV:]` nel prompt, anteprima sfocata servita dal backend, sblocco con pagamento simulato registrato in `simulated_payments`, toggle+prezzo per personaggio e invio manuale bloccato.

### 14.2 Notifiche e realismo temporale — FATTO (13 settembre 2026)

- Risposte non immediate: ritardo casuale configurabile per personaggio/fan (min-max, distribuzione realistica, "sta scrivendo…").
- Orari di attività del personaggio (fasce orarie, giorni), con coda dei messaggi generati da consegnare al momento giusto.
- Notifiche interne al playground (badge conversazione non letta, suono opzionale); niente notifiche esterne.
- Backend: job programmati (stesso pattern della coda `jobs`) con `deliver_at`, stato `scheduled/sent`.
- Implementato: ritardo casuale per personaggio (min/max), orari di attività con giorni, coda `scheduled_replies` consegnata dallo scheduler nell'API, "sta per rispondere…" in chat, badge non letti per conversazione e segna-come-letto all'apertura. Niente notifiche esterne.

### 14.3 Playground video

- Terza/quarta scheda per generazione video con i modelli già installati (LTX-Video, Wan 2.x).
- Flusso i2v da immagine approvata della libreria, più text-to-video per test.
- Cura dei risultati (approva/scarta/elimina), libreria video per personaggio, stesso pattern della libreria immagini.
- Prerequisito già pronto: il dataset Telegram scarica anche i video e li marca `kind=video` con anteprima, da usare per le pose.
- Metriche GPU e tempi dedicati (i video sono molto più pesanti).
- **Nota (18 settembre 2026)**: modelli LTX 2.3 riscaricati e completati (dev fp8 29.1 GB, distilled fp8 29.5 GB, distilled LoRA); resta mancante solo la LoRA Gemma abliterated citata dai workflow LTX dell'utente (da reinserire a mano o rimuovere dal grafo). Wan 2.2 i2v + LoRA lightx2v restano installati come via pronta. Generazione ora parallela su 4 GPU (4 istanze ComfyUI, porte 8188-8191).

### 14.4 Filtro modelli nelle UI — FATTO (13 settembre 2026)

- Chat: mostrare solo LLM conversazionali; escludere modelli di coding, embedding e generazione video.
- Immagini: mostrare solo checkpoint SDXL/SD1.5 fotografici o anime; escludere modelli video (LTX/Wan) e pipeline non compatibili.
- Implementato: `kind` (chat/coding/embedding) per i modelli Ollama; metadati `{name, family, usable}` per i checkpoint ComfyUI (Pony/Anime/Reale/Video), con i modelli video esclusi dal selettore.

### 14.5 Temi colore per playground — FATTO (13 settembre 2026)

- Palette distinta per Chat, Immagini, Dataset (e futuro Video) per orientarsi a colpo d'occhio.
- Implementato: accenti diversi per Chat (teal), Immagini (viola) e Dataset (verde) tramite variabili CSS `--accent`.

### 14.6 Flusso Image Playground: personaggio -> dataset -> LoRA

Idea dell'utente. Decisioni prese (13 settembre 2026): famiglia primaria **real** (PornMaster/LUSTIFY), trainer **kohya sd-scripts** su venv dedicato host, pose via **ControlNet OpenPose**, ranking identità con **ArcFace (InsightFace)**, una famiglia primaria per personaggio + retrain on-demand per le altre, fallback IPAdapter quando manca la LoRA.

**Fase A — registry e training (FATTO 13 settembre 2026)**:
1. Migrazione `0012_lora_pipeline`: `character_loras`, `lora_datasets`, `lora_dataset_items`, `pose_references`, `training_jobs`.
2. API `/api/characters/{id}/loras`, `/api/loras/*`, `/api/training-jobs` (claim/progress/complete/cancel) + scheda **LoRA** (ambra) con stato e avanzamento live.
3. Trainer host: `scripts/trainer/setup.sh` (venv 3.12 + torch cu124 + kohya) e `scripts/trainer/train_worker.py` (poll coda, GPU libera, log, copia artefatti, recovery job stale); unit systemd pronta in `scripts/trainer/ai-influencer-trainer.service`.
4. Verifica end-to-end completata (15 settembre 2026): LoRA "Nikita real v1" (20 immagini, rank 16, 1000 step, loss finale 0.0738, ~41 min su GPU 1) addestrata dal worker, copiata in ComfyUI e in `data/loras/`, attivata; generazione di validazione con LoRA (peso 0.85) che conferma il trasferimento dell'identità in una scena nuova. Il worker ora sopravvive ai riavvii dell'API (errori di rete gestiti).

**Fase B — dataset builder**: pose extraction (OpenPose → `pose_references`), batch di candidati con anchor IPAdapter + ControlNet, ranking ArcFace, selezione, caption editabili, gate ≥20.

**Fase C — wizard 14.6**: creazione personaggio → 5 candidati → anchor → loop pose → dataset → training → validazione → attivazione. Il flusso richiesto è dettagliato in **§14.16**, che diventa il riferimento operativo per le Fasi B e C.

**Fase D — uso**: `resolve(character, checkpoint)` in playground immagini/chat/avatar, peso LoRA e versioni.

I punti 1-4 originali restano validi; le questioni aperte (GPU, export, soglia QC, versioni) sono risolte dalle decisioni sopra.

### 14.7 Fix classificazione dataset — FATTO (15 settembre 2026)

Premendo **Classifica non classificate** la classificazione riparte per tutte le foto senza descrizione (`pending` + `failed`); le già pronte non vengono toccate e un run interrotto riparte dopo 10 minuti.

### 14.8 Checkbox dopo il testo — FATTO (15 settembre 2026)

Casella a destra del testo (inline) per "Classify with AI after import", "PPV photos", "Activity hours" e tutte le checkbox `.auto-label` (regola CSS globale: checkbox larghezza automatica).

### 14.9 Eliminare le conversazioni — FATTO (15 settembre 2026)

Pulsante × su ogni riga della lista conversazioni (con conferma); elimina messaggi, foto e risposte in coda. L'endpoint `DELETE /api/conversations/{id}` esisteva già (era nascosto nelle Opzioni della chat aperta).

### 14.10 Liberare la VRAM delle GPU — FATTO (15 settembre 2026)

Pulsante **Libera VRAM** sotto il pannello GPU: `POST /api/system/free-vram` scarica i modelli Ollama (`keep_alive=0`) e chiama `/free` su ComfyUI (`unload_models` + `free_memory`).

### 14.11 Human mode nella chat — FATTO (15 settembre 2026)

Checkbox **Human mode** nella barra chat (a sinistra del testo, per conversazione):

- risposte multiple in sequenza (2-3 messaggi brevi) con refusi occasionali e correzione (`*parola`);
- messaggi spontanei: dopo una risposta viene programmato un follow-up casuale (15-60 min, dentro gli orari di attività), uno solo finché il fan non risponde;
- la UI aggiorna la chat ogni 15 s quando Human mode è attivo, per mostrare i messaggi spontanei in arrivo.

### 14.12 Fix pulsante "Classifica" per dataset incompleti — FATTO (15 settembre 2026)

Il pulsante ora **forza il riavvio**: le immagini senza descrizione (`pending`+`failed`) vengono riprocessate anche se la fonte è bloccata in `classifying` (nessuna attesa di 10 minuti); una guardia in-process evita doppi lavori e la UI avvisa "Classificazione già in corso" se si preme durante un run attivo. Verificato sul dataset `EvaElfie` bloccato (173/297): ripartito e ripreso in background.

### 14.13 Spostare "Foto profilo" nella scheda LoRA — FATTO (15 settembre 2026)

La generazione della foto profilo è ora nella scheda **LoRA** (anteprima del personaggio, pulsante Genera/Rigenera, visore a schermo intero); nel pannello chat resta solo la visualizzazione.

### 14.14 Supporto checkpoint e LoRA FLUX.2 e Qwen Image — FATTO (15 settembre 2026)

- Discovery modelli estesa: `GET /api/images/checkpoints` unisce `CheckpointLoaderSimple` e `UNETLoader` con famiglia `qwen-image`, `z-image`, `flux2` (oltre a real/pony/anime/video) e `usable`.
- Workflow programmatici per famiglia (niente JSON SDXL): **Qwen-Image** (UNETLoader + qwen_2.5_vl + vae, AuraFlow shift 3, CFGNorm, 20 step cfg 2.5), **Z-Image** (turbo 4 step cfg 1 / base 30 step cfg 4, sampler `res_multistep`, CLIP type `lumina2`), **FLUX.2 dev** (Mistral fp8, flux2 VAE, turbo LoRA, `SamplerCustomAdvanced` + `Flux2Scheduler`, 8 step cfg 1).
- IPAdapter/ControlNet/LoRA personaggio restano solo SDXL (le famiglie nuove generano testo→immagine; Qwen-Image-Edit resta dedicato alle variazioni dataset).
- Validato con generazioni reali: Z-Image turbo 41 s, FLUX.2 183 s (primo caricamento 53 GB). Selettori Immagini/LoRA/chat mostrano le nuove famiglie; la LoRA automatica del personaggio non si applica a queste famiglie.

### 14.15 Scheda "Home" — FATTO (15 settembre 2026)

Al posto della scheda "Models" c'è una scheda **Home** (pagina iniziale su `/`; la chat si sposta su `/chat`) con:

- **flag di stato** verde/giallo/rosso per i punti che possono rompersi: API+database, ComfyUI, Ollama, telemetria GPU, worker di training (heartbeat) — per il debug rapido;
- **GPU in tempo reale** (memoria, utilizzo, potenza, temperatura, processi; aggiornate ogni 5 s);
- **personaggi** con foto profilo, stile e numero di LoRA, link diretto alla chat;
- **modelli disponibili**: checkpoint ComfyUI (famiglia, compatibilità), LoRA ComfyUI, modelli Ollama (tipo, dimensione);
- aggiornamento manuale + timestamp.

Nota: la "mappa combinazioni checkpoint ↔ LoRA" prevista in origine resta da fare e si aggiungerà alla Home o alla scheda LoRA (vedi 14.14 compatibilità).

### 14.16 Pipeline LoRA completa nella scheda LoRA (spec integrata, 15 settembre 2026)

Estende/sostituisce Fase B e C di 14.6. Regola: **estendere l'esistente, niente riscritture**; solo personaggi adulti sintetici, nessuna likeness reale.

**Principio di separazione**: Identità, Posa, Stile, Outfit, Scena, Camera e Luce sono concetti indipendenti; la generazione è `identità + posa (ControlNet) + stile + outfit + scena/camera/luce`. La posa non si controlla con img2img né con pose-LoRA come sistema primario.

**Stato (prima slice, 15 settembre 2026)**: estrazione posa con **DWPose** e **Pose Library** implementate — API `/api/poses` (extract/list/patch/delete/skeleton/source), pulsante **Estrai posa** nel dettaglio immagine della scheda Dataset, griglia **Pose Library** nella scheda LoRA (rinomina/attiva/elimina), guardia "nessuna persona rilevata". Modelli di posa installati (ControlNet OpenPose SDXL + DWPose); checkpoint immagine ridotti al solo PornMaster (110 GB liberati).

**Stato (seconda slice, 15 settembre 2026)**: generazione dataset guidata dalla posa — workflow `chat_real_pose.json` / `chat_real_pose_reference.json` (ControlNet OpenPose + IPAdapter), API `/api/datasets` (create/list/detail/generate/patch/delete item), training **da dataset** (`dataset_id` → materializzazione automatica in `data/lora_datasets/<stem>` con caption+trigger), UI **Dataset** nella scheda LoRA (crea dataset, genera candidati con pose, cura con selezione/caption/eliminazione, scelta dataset nel form di training). Verificato con una generazione reale identità+posa.

**Stato (terza slice, 15 settembre 2026)**: riorganizzazione secondo il modello di lavoro dell'utente — **la posa è conditioning di generazione (ControlNet), non un dato di training**: la **Pose Library** e la selezione posa sono nella scheda **Immagini** (la generazione libreria accetta `pose_ids`/`pose_strength` e cicla le pose scelte), mentre la scheda **LoRA** resta creazione personaggio + dataset + training. Flusso obiettivo LoRA: reference (`Qwen`/`Z-Image`/`SDXL`) → variazioni con **Qwen-Image-Edit** ("same person, …") → filtro manuale → **LoRA SDXL**. Download avviati in background: **LUSTIFY** (SDXL realistic), **Qwen-Image** base, **FLUX.2** (diffusion + text encoder Mistral + VAE + turbo LoRA); **Qwen-Image-Edit 2509**, **Z-Image** e turbo sono già installati.
Da fare per completare il flusso: workflow/endpoint **Qwen-Image-Edit** per le variazioni del dataset ("stessa persona, ..."), supporto modelli **Qwen-Image / Z-Image / FLUX.2** nella scheda Immagini (famiglie, workflow, selettori) e rimozione dei marker `unsupported` sui nuovi modelli.

**Stato (quarta slice, 15 settembre 2026)**: **variazioni Qwen-Image-Edit** implementate — `qwen_image_edit()` (Qwen-Image-Edit 2509 fp8 + Lightning 4-step, TextEncodeQwenImageEditPlus + ModelSamplingAuraFlow + CFGNorm), endpoint `POST /api/datasets/{id}/variations` (una scena per riga, count 1-4, seed/steps/cfg/lora_weight), blocco **Variazioni** nella scheda LoRA → Dataset. Validato con una generazione reale: stessa identità, scena nuova, 4 step. Download in corso: FLUX.2 (diffusion ~33 GB + text encoder + VAE + turbo LoRA); Qwen-Image base e LUSTIFY completati; LoRA 2511 Lightning ripristinata.


**Stato (quinta slice, 15 settembre 2026)**: **annullamento generazione** (`POST /api/images/interrupt` → ComfyUI `/interrupt` + coda pulita, con errore "Generazione annullata" riconosciuto dal backend) disponibile in tutte le UI di generazione (immagini, dataset/variazioni, foto in chat, avatar LoRA); brand WebUI **v5**; scheda **LoRA** riorganizzata in tre step — **1 Personaggio** (foto profilo, duplica/elimina, "+" nuovo personaggio con form qui), **2 Dataset LoRA** (variazioni + curatela), **3 Training** (crea LoRA + accoda con dataset, job con avanzamento). Il "+" di creazione personaggio è stato tolto dalla chat.

**Stato (sesta slice, 15 settembre 2026)**: foto profilo con **scelta del modello** (`POST /api/characters/{id}/avatar` con `checkpoint`), **modifica con Qwen-Image-Edit** (`POST /api/characters/{id}/avatar/edit`) o **rigenerazione da zero**; il "+" nuovo personaggio è nella **barra sinistra** della scheda LoRA; aggiunti hint UI che spiegano **candidati (SDXL+IPAdapter)** vs **variazioni (Qwen-Edit)** e il significato del **rank**.

**Stato (settima slice, 15 settembre 2026)**: **analisi qualità dataset** (`GET /api/datasets/{id}/analysis`): progresso verso 20 selezionate, duplicati via phash, copertura pose, keyword (full body, profilo, frontale, standing/sitting/lying, outdoor/indoor, giorno/notte) e avvisi localizzati nella UI; **LoRA personaggio automatica** nella scheda Immagini (all'apertura si attiva la LoRA attiva della famiglia del checkpoint con peso 0.85 e la UI lo segnala).

**Stato (ottava slice, 15 settembre 2026)**: **multi-LoRA** con categorie (Personaggio/Stile/Outfit/Composizione/Altro) e **CLIP weight** per riga (`apply_loras` imposta `strength_clip`); **preset di generazione** persistenti (`generation_presets`, CRUD API + UI: applica/salva/elimina nella scheda Immagini); **filtro compatibilità** LoRA nel selettore (famiglie dedotte da nome/cartella: le LoRA incompatibili col checkpoint vengono nascoste e conteggiate). Fatto anche: scelta del modello per step (variazioni/candidati), pose nei candidati SDXL, obiettivo dataset 40, guida utente nella scheda LoRA, generazione parallela su 4 GPU. Restano dai punti §14.16: rigenera/stesso seed per item, carica impostazioni dall'immagine, reference canonical/face/full-body.

**Stato (nona slice, 18 settembre 2026)**: pipeline dataset **a reference canoniche** — flusso: (1) 20-50 candidati identità con **Qwen-Image-2512**, (2) cura e scelta di **4-8 reference** con ruoli (`close_face`, `three_quarter_face`, `profile`, `upper_body`, `front_full_body`, `three_quarter_full_body`, `side_full_body`), (3) due **rami indipendenti** — variazioni **Qwen-Image-Edit** e candidati **SDXL + IPAdapter + DWPose/ControlNet** — entrambi nella stessa griglia di cura fino a 50-70 immagini finali (target 60). Migrazione `0015`; le reference alimentano entrambi i rami (rotazione sulle reference, fallback alla foto profilo).

**Da riusare (già presente)**: scheda LoRA con registry e coda training; worker kohya; tabelle `character_loras`, `lora_datasets`, `lora_dataset_items`, `pose_references`, `training_jobs`; `image_library` con metadati (prompt, seed, checkpoint, loras, tag, phash); IPAdapter; workflow JSON parametrizzati per famiglia; modello `Influencer` (niente nuovo modello Character: si estende).

**Funzionalità da implementare**

1. **Gestione personaggio (estesa)**: trigger word, reference multiple (canonical/face/full-body), checkpoint preferito, LoRA associate, dataset collegati; duplica/elimina già spostati nella scheda LoRA.
2. **Creazione personaggio**: checkpoint, prompt/negative, dimensioni, seed/random, sampler, scheduler, steps, CFG, batch; candidati selezionabili come reference. Riusare i controlli del playground immagini.
3. **Workflow template**: i JSON in `workflows/` restano il registry; aggiungere varianti *character_reference*, *pose_generation*, *dataset_generation*, *multi_lora*; parametri iniettati dal backend (`checkpoint`, prompt, seed, sampler, steps, CFG, risoluzione, LoRA+pesi, pose image, ControlNet strength, identity reference+strength). Nessun node ID nel frontend.
4. **Posa**: upload immagine o scelta dalla libreria, estrazione skeleton con DWPose/OpenPose (`comfyui_controlnet_aux` già installato; serve il ControlNet SDXL), preview skeleton, forza/start/end, enable. Se i nodi mancano, messaggio chiaro e fallback su skeleton esistente.
5. **Pose library**: usa `pose_references` (nome, thumbnail, skeleton, tag, data); salva/rinomina/tagga/elimina/seleziona; niente file duplicati.
6. **Identity reference**: IPAdapter oggi; FaceID/InstantID opzionali con capability detection; controlli separati dalla posa; opzionale quando esiste la LoRA.
7. **Dataset generation**: ricette/preset di variazione (Portrait, Full-body, Profile, Outdoor, Indoor, Night, Pose-library): inquadratura, angolo, posa, ambiente, luce, outfit, espressione, altezza/distanza camera, focale. Niente combinazioni casuali cieche.
8. **Metadata dataset item**: estendere `lora_dataset_items` con prompt, negative, seed, checkpoint, loras, pose, identity reference, sampler, scheduler, steps, cfg, dimensioni, workflow JSON, tag; percorsi relativi; nessuna immagine duplicata in DB.
9. **Curation**: approva/rifiuta/preferito/elimina/apri/vedi metadata/rigenera/**stesso seed**/carica impostazioni; filtri per stato, posa, angolo, full-body/portrait, outfit, scena, batch; scorciatoie tastiera; obiettivo 40–80 immagini curate (qualità > quantità).
10. **Quality warnings**: statistiche deterministiche (troppi frontali, pochi profili/full-body, outfit/sfondo/posa ripetuti, poca diversità luce/camera, duplicati via `average_hash` già esistente).
11. **Training**: riuso del worker kohya; job creato **da dataset curato** (`dataset_id`, oggi serve `images_dir`); parametri base/avanzati (rank/alpha/lr/optimizer/steps/risoluzione/batch/caption/output name), default sensati; output tipo `nakita_character_v1.safetensors`; QC volto ArcFace prima di attivare.
12. **Training job management**: già presente (stati queued/running/completed/failed/cancelled, progress, log, errori); aggiungere epoch/step/loss nel progress e consultazione log.
13. **Multi-LoRA generation**: stack con enable/disable, selezione, categoria (Character/Style/Outfit/Composition/Other), weight modello e CLIP, rimozione e riordino; pesi liberi (es. character 0.85 + style 0.35 + outfit 0.45 + ControlNet 0.80 + identity 0.50).
14. **Compatibilità modello/LoRA**: validazione per famiglia con metadata safetensors (header), convenzioni di cartella e `object_info`; warning soft quando non determinabile, blocco solo se certamente incompatibile (SDXL↔FLUX, ecc.).
15. **Preset di generazione**: CRUD (checkpoint, character, LoRA+pesi, posa/strength, identity, sampler, scheduler, steps, CFG, risoluzione, frammenti prompt, negative).
16. **Riproducibilità**: per ogni immagine salvare workflow JSON completo + tutti i parametri; "carica impostazioni dall'immagine"; riusare i metadati PNG di ComfyUI; non rimuovere metadata utili.
17. **ComfyUI client**: resta centralizzato in `app/integrations/comfyui.py` (già fa discovery modelli/LoRA e submit); aggiungere se serve history/cancel/queue; niente secondo client.
18. **Capability detection**: ControlNet/DWPose/IPAdapter/FaceID/training → available/unavailable/parziale con messaggi tipo "DWPose non rilevato: estrazione posa non disponibile, puoi comunque usare uno skeleton esistente".
19. **UI**: la scheda LoRA si organizza in sub-sezioni **Characters, Dataset, Pose Library, Training, Generate** (la panoramica modelli resta nella scheda Home, 14.15); dentro Generate separare visivamente CHARACTER/POSE/STYLE/OUTFIT/SCENE/CAMERA/ADVANCED (collassabili). Form niente monoliti.
20. **Stato**: usare lo stato React esistente; nessuna nuova libreria.

**Ordine di implementazione (vertical slices)**: 1) discovery modelli/worker (fatto) → 2) estensione character (trigger/reference/checkpoint) → 3) generazione reference + selezione → 4) posa (ControlNet+DWPose) → 5) identity reference → 6) dataset generation + metadata → 7) curation + warning → 8) multi-LoRA → 9) riproducibilità/load settings → 10) training da dataset → 11) preset → 12) compatibilità → 13) capability detection/UX → 14) test end-to-end.

**Definition of done (flusso minimo)**: crea personaggio → genera/scegli reference canonical → scegli posa → genera più immagini dello stesso personaggio in configurazioni diverse → rivedi e approva i candidati → avvia training dal dataset curato → LoRA rilevata → seleziona Character LoRA + Style + Outfit + posa + identity opzionale → genera l'immagine finale → salva metadata → ricarica le impostazioni dall'immagine.

**Errori/UX/sicurezza/performance**: messaggi utili (checkpoint/LoRA/nodo mancante, incompatibilità), logging tracciabile delle azioni backend, upload validati (tipo/estensione/percorso, anti path traversal), galleria con thumbnail/lazy loading e cache della discovery modelli.

## 15. Domande aperte

1. Numero di personaggi contemporanei e modello multi-account (agenzia?).
2. Provider di object storage preferito (MinIO locale vs cloud).
3. Qualità video attesa per partire (LTX veloce vs Wan/Hunyuan di qualità).
4. Modello LLM per caption/chat definitivo (locale grande vs più modelli specializzati).
5. Politica di prezzo e gestione refund/chargeback su Fanvue.
