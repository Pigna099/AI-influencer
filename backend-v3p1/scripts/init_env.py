"""Initialize only missing local secrets; never replace an existing .env."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if not path.exists():
    path.write_text(
        f"API_KEY={secrets.token_urlsafe(32)}\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\n"
        "TEXT_PROVIDER=ollama\nIMAGE_PROVIDER=mock\nOLLAMA_URL=http://127.0.0.1:11434\n"
        "OLLAMA_MODEL=llama3.1:8b\nOLLAMA_TIMEOUT_SECONDS=180\n"
    )
    path.chmod(0o600)
    print("Creato .env. La chiave di accesso è nel file riservato.")
(root / "data/media").mkdir(parents=True, exist_ok=True)
