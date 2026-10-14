"""Legacy message catalog (compatibility shim).

Backend messages are written in English at the source. This catalog is kept so
older clients sending `X-Language: en` keep working; unknown strings pass
through unchanged.
"""

TRANSLATIONS: dict[str, str] = {
    "Item not found": "Item not found",
    "Select an installed chat-capable model": "Select an installed chat-capable model",
    "The character was modified: reload the page": "The character was modified: reload the page",
    "ComfyUI is unreachable: start the image service": "ComfyUI is unreachable: start the image service",
    "Could not save the profile picture": "Could not save the profile picture",
    "Checkpoint not installed in ComfyUI": "Checkpoint not installed in ComfyUI",
    "Profile picture unavailable": "Profile picture unavailable",
    "Image unavailable": "Image unavailable",
    "A reply is in progress. Wait before changing or deleting the chat.": (
        "A reply is in progress. Wait before changing or deleting the chat."
    ),
    "The character is already replying in this conversation": (
        "The character is already replying in this conversation"
    ),
    "Chat photos are disabled": "Chat photos are disabled",
    "The character has generations in progress": "The character has generations in progress",
    "Il modello non ha restituito una descrizione valida. Prova un altro modello.": (
        "The model did not return a valid description. Try another model."
    ),
    "Un confronto deve mantenere personaggio, fan, messaggio e temperatura uguali": (
        "A comparison must keep character, fan, message and temperature the same"
    ),
    "The model produced no visible reply within the token limit.": (
        "The model produced no visible reply within the token limit."
    ),
    "The workflow has no CheckpointLoaderSimple node": (
        "The workflow has no CheckpointLoaderSimple node"
    ),
    "Invalid access key": "Invalid access key",
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
