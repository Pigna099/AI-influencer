# Collegare ComfyUI

Non è incluso un workflow inventato: deve corrispondere ai modelli e ai nodi installati sul tuo server.

1. Prova una generazione in ComfyUI ed esporta il workflow in **formato API**.
2. Salvalo come `workflows/default.json`.
3. Sostituisci i valori degli input appropriati con queste stringhe complete:
   - testo del prompt positivo: `"{{positive_prompt}}"`
   - testo del prompt negativo: `"{{negative_prompt}}"`
   - seed del sampler: `"{{seed}}"`
   - batch_size del latent: `"{{image_count}}"`
4. Usa un solo nodo SaveImage finale. Il backend controlla che il numero di immagini coincida con la richiesta.
5. Imposta `IMAGE_PROVIDER=comfyui` e l'indirizzo `COMFYUI_URL` in `.env`, poi ricrea API e worker.

Il backend sostituisce i valori nel JSON preservando i tipi: seed e quantità diventano numeri.
Il token LoRA nella descrizione aiuta il prompt, ma NON carica una LoRA: il workflow deve contenere il nodo LoRA con il file corretto.
Sono supportate immagini; video e workflow con più output richiedono un'estensione.
