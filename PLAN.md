# PLAN — Da playground a influencer autonoma

Piano di lavoro per trasformare il playground (`backend-v3p1`) in una piattaforma che genera contenuti, pubblica su Instagram e gestisce i fan su Fanvue con vendita di foto/video.

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

| Componente | File (backend-v3p1) | Riuso |
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

## 14. Domande aperte

1. Numero di personaggi contemporanei e modello multi-account (agenzia?).
2. Provider di object storage preferito (MinIO locale vs cloud).
3. Qualità video attesa per partire (LTX veloce vs Wan/Hunyuan di qualità).
4. Modello LLM per caption/chat definitivo (locale grande vs più modelli specializzati).
5. Politica di prezzo e gestione refund/chargeback su Fanvue.
