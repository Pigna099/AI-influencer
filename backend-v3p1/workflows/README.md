# Collegare ComfyUI

Il backend usa workflow diversi:

- `workflows/default.json`: contenuti della pipeline legacy (`/content-jobs`), generati dal worker.
- `workflows/chat_real.json` e `chat_anime.json`: foto in chat e immagine profilo per i due stili selezionabili dal personaggio.
- `workflows/chat_real_reference.json` e `chat_anime_reference.json`: varianti con IPAdapter usate quando il personaggio ha un'immagine profilo.
- `workflows/chat_default.json` e `chat_reference.json`: fallback legacy.

### Stili immagine

Lo **Stile foto** nella colonna del personaggio sceglie la coppia di workflow:

- **Reale** (`chat_real*`): checkpoint `lustifySDXLNSFWSFW_v20.safetensors` (LUSTIFY v2, NSFW fotorealistico), sampler DPM++ 2M Karras, 30 passi, CFG 5.5, CFG scale, 832×1216.
- **Anime** (`chat_anime*`): checkpoint `NoobAI-XL-v1.1.safetensors` (NSFW anime/Illustrious), Euler a, 32 passi, CFG 5.0, CLIP skip -2.

Entrambi i workflow includono:

1. **Hires fix** da 832×1216 a 1216×1824 (`LatentUpscale` + secondo `KSampler`, denoise 0.45–0.5): più dettaglio senza artefatti.
2. **FaceDetailer** con `bbox/face_yolov8m.pt` per rifinire il volto.
3. **Dettaglio mani** con `bbox/hand_yolov8s.pt` (FaceDetailer concatenato).

I modelli dei detector sono già in `models/ultralytics/`. Il prompt è costruito dal backend in inglese: lo stile reale usa descrizioni fotografiche, quello anime tag Danbooru (`masterpiece, best quality, ...`). Le scene scritte in italiano dal modello vengono tradotte automaticamente prima della generazione.

Per cambiare modello, stile o parametri, modifica i JSON e le variabili `.env` (`CHAT_REAL_STYLE`, `CHAT_REAL_NEGATIVE`, `CHAT_ANIME_STYLE`, `CHAT_ANIME_NEGATIVE`, `CHAT_REAL_WORKFLOW_PATH`, ...), poi ricrea API e worker.

Entrambi devono essere esportati da ComfyUI in **formato API** e sostituire i valori degli input con queste stringhe complete:

- testo del prompt positivo: `"{{positive_prompt}}"`
- testo del prompt negativo: `"{{negative_prompt}}"`
- seed del sampler: `"{{seed}}"`
- batch_size del latent: `"{{image_count}}"`

Il workflow della chat può anche contenere `"{{reference_image}}"` in un nodo `LoadImage`: in quel caso il backend carica l'immagine profilo del personaggio su ComfyUI (`/upload/image`) e la usa come riferimento, per esempio con IPAdapter o img2img. Se il workflow ha il placeholder ma il personaggio non ha ancora una foto profilo, la generazione fallisce con un errore esplicito.

### Workflow con riferimento (IPAdapter)

`workflows/chat_reference.json` è il workflow usato quando il personaggio ha un'immagine profilo e il file esiste. Contiene:

- `LoadImage` con `"{{reference_image}}"` (l'immagine profilo caricata dal backend);
- `easy ipadapterApplyADV` (nodo di **ComfyUI-Easy-Use**) con preset `PLUS (high strength)` che patcha il modello;
- il `KSampler` collegato all'output `MODEL` del nodo IPAdapter.

Easy-Use scarica da solo `ip-adapter-plus_sdxl_vit-h.safetensors` e `clip-vit-h-14-laion2B-s32B-b79K.safetensors` in `models/ipadapter/` alla prima generazione (circa 3,4 GB in totale). Valori verificati: **reale** weight 0.6, **anime** weight 0.5, `embeds_scaling: "K+V"`, `weight_type: "ease in-out"`. Valori più alti o `V only` producono artefatti su NoobAI. Se il workflow di riferimento non esiste o il personaggio non ha una foto profilo, si usa il workflow semplice.

Il campo `ckpt_name` di ogni nodo `CheckpointLoaderSimple` viene sovrascritto dal checkpoint scelto per il personaggio nella webUI, se presente.

Usa un solo nodo SaveImage finale: il backend controlla che il numero di immagini coincida con la richiesta. Il backend sostituisce i valori nel JSON preservando i tipi: seed e quantità diventano numeri.

Configurazione in `.env`:

```bash
IMAGE_PROVIDER=comfyui
COMFYUI_URL=http://127.0.0.1:8188
CHAT_WORKFLOW_PATH=workflows/chat_default.json
CHAT_IMAGE_ENABLED=true
CHAT_IMAGE_NSFW=true
CHAT_IMAGE_COOLDOWN_SECONDS=300
```

Il prompt delle foto è costruito dal backend: profilo del personaggio (`appearance`), scena richiesta dal modello e stile NSFW configurato (`CHAT_IMAGE_STYLE`, `CHAT_IMAGE_NEGATIVE`). I prompt negativi includono sempre `child, minor, teen, underage`: i personaggi sono adulti e le immagini generate devono restare tali. Per cambiare modello o stile, modifica il workflow e le variabili `.env`, poi ricrea API e worker.

Il token LoRA nella descrizione aiuta il prompt, ma NON carica una LoRA: il workflow deve contenere il nodo LoRA con il file corretto. Sono supportate immagini; video e workflow con più output richiedono un'estensione.
