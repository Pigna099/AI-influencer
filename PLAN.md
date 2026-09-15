# PLAN — Da playground a influencer autonoma

Piano di lavoro per trasformare il playground (`backend-v4p1`) in una piattaforma che genera contenuti, pubblica su Instagram e gestisce i fan su Fanvue con vendita di foto/video.

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

| Componente | File (backend-v4p1) | Riuso |
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
4. Verifica end-to-end: LoRA "Nikita" real v1 (20 immagini generate con anchor IPAdapter, rank 16, PornMaster) addestrata, copiata in ComfyUI e in `data/loras/`, validazione con generazione.

**Fase B — dataset builder**: pose extraction (OpenPose → `pose_references`), batch di candidati con anchor IPAdapter + ControlNet, ranking ArcFace, selezione, caption editabili, gate ≥20.

**Fase C — wizard 14.6**: creazione personaggio → 5 candidati → anchor → loop pose → dataset → training → validazione → attivazione.

**Fase D — uso**: `resolve(character, checkpoint)` in playground immagini/chat/avatar, peso LoRA e versioni.

I punti 1-4 originali restano validi; le questioni aperte (GPU, export, soglia QC, versioni) sono risolte dalle decisioni sopra.

### 14.7 Fix classificazione dataset (richiesto 13 settembre 2026)

Premendo **Classifica in attesa**, la classificazione deve ripartire per tutte le foto non ancora classificate (non solo le `pending`: includere/riprovare anche `failed` e quelle senza descrizione), non fermarsi alle già pronte.

### 14.8 Checkbox dopo il testo, non sopra (richiesto 13 settembre 2026)

Spostare la casella a destra/dopo l'etichetta (non sopra o a sinistra) per: "Classify with AI after import" (Dataset), "PPV photos" (personaggio), "Activity hours" (realismo). Verificare tutte le checkbox delle UI per coerenza.

### 14.9 Eliminare le conversazioni (richiesto 13 settembre 2026)

Aggiungere un pulsante per eliminare una conversazione dalla lista chat (con conferma), con pulizia di messaggi, foto e stato correlati.

### 14.10 Liberare la VRAM delle GPU (richiesto 13 settembre 2026)

Pulsante (nel pannello GPU in tempo reale) per scaricare i modelli residenti e liberare la VRAM: unload dei modelli Ollama e reset della cache di ComfyUI, con stato dell'operazione.

### 14.11 Human mode nella chat (richiesto 13 settembre 2026)

Modalità "Human mode" (checkbox a sinistra) per rendere la chat più umana:

- risposte multiple in sequenza (più messaggi brevi invece di un unico blocco), con refusi/correzioni occasionali (`*correzione`) e pause tra i messaggi;
- in questa modalità il personaggio può inviare spontaneamente un nuovo messaggio per riprendere la conversazione (messaggi proattivi casuali, coerenti con memoria e orari di attività);
- toggle per conversazione e default per personaggio.

## 15. Domande aperte

1. Numero di personaggi contemporanei e modello multi-account (agenzia?).
2. Provider di object storage preferito (MinIO locale vs cloud).
3. Qualità video attesa per partire (LTX veloce vs Wan/Hunyuan di qualità).
4. Modello LLM per caption/chat definitivo (locale grande vs più modelli specializzati).
5. Politica di prezzo e gestione refund/chargeback su Fanvue.
