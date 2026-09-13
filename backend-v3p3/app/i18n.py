"""Small message catalog so API errors can follow the UI language.

The frontend sends `X-Language` (it/en). Messages are written in Italian and
translated on the way out; unknown strings pass through unchanged.
"""

TRANSLATIONS: dict[str, str] = {
    "Elemento non trovato": "Item not found",
    "Seleziona un modello installato capace di generare chat": "Select an installed chat-capable model",
    "Il personaggio è stato modificato: ricarica la pagina": "The character was modified: reload the page",
    "ComfyUI non è raggiungibile: avvia il servizio immagini": "ComfyUI is unreachable: start the image service",
    "Impossibile salvare l'immagine profilo": "Could not save the profile picture",
    "Checkpoint non installato in ComfyUI": "Checkpoint not installed in ComfyUI",
    "Immagine profilo non disponibile": "Profile picture unavailable",
    "Immagine non disponibile": "Image unavailable",
    "Una risposta è in corso. Attendi prima di modificare o eliminare la chat.": (
        "A reply is in progress. Wait before changing or deleting the chat."
    ),
    "Il personaggio sta già rispondendo in questa conversazione": (
        "The character is already replying in this conversation"
    ),
    "Le foto in chat sono disattivate": "Chat photos are disabled",
    "Il personaggio ha generazioni in corso": "The character has generations in progress",
    "Il modello non ha restituito una descrizione valida. Prova un altro modello.": (
        "The model did not return a valid description. Try another model."
    ),
    "Un confronto deve mantenere personaggio, fan, messaggio e temperatura uguali": (
        "A comparison must keep character, fan, message and temperature the same"
    ),
    "Il modello non ha prodotto una risposta visibile entro il limite di token.": (
        "The model produced no visible reply within the token limit."
    ),
    "Il workflow non contiene un nodo CheckpointLoaderSimple": (
        "The workflow has no CheckpointLoaderSimple node"
    ),
    "Chiave di accesso non valida": "Invalid access key",
}

PREFIXES: list[tuple[str, str]] = [
    ("Generazione immagine profilo non riuscita: ", "Profile picture generation failed: "),
    ("Generazione foto non riuscita: ", "Photo generation failed: "),
]


def translate_detail(detail, language: str | None):
    if language != "en" or not isinstance(detail, str):
        return detail
    if detail in TRANSLATIONS:
        return TRANSLATIONS[detail]
    for italian, english in PREFIXES:
        if detail.startswith(italian):
            return english + detail[len(italian) :]
    return detail
