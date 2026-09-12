# Collegare ComfyUI

Il backend usa due workflow diversi:

- `workflows/default.json`: contenuti della pipeline legacy (`/content-jobs`), generati dal worker.
- `workflows/chat_default.json`: foto inviate in chat e immagine profilo del personaggio. È già configurato per il checkpoint NSFW SDXL `ponyDiffusionV6XL_v6StartWithThisOne.safetensors`; adatta `ckpt_name` e i nodi ai modelli installati sul tuo server.

Entrambi devono essere esportati da ComfyUI in **formato API** e sostituire i valori degli input con queste stringhe complete:

- testo del prompt positivo: `"{{positive_prompt}}"`
- testo del prompt negativo: `"{{negative_prompt}}"`
- seed del sampler: `"{{seed}}"`
- batch_size del latent: `"{{image_count}}"`

Il workflow della chat può anche contenere `"{{reference_image}}"` in un nodo `LoadImage`: in quel caso il backend carica l'immagine profilo del personaggio su ComfyUI (`/upload/image`) e la usa come riferimento, per esempio con IPAdapter o img2img. Se il workflow ha il placeholder ma il personaggio non ha ancora una foto profilo, la generazione fallisce con un errore esplicito.

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
