import secrets

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from .config import settings

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key: str | None = Depends(key_header)):
    if not settings.api_key:
        raise HTTPException(503, "Configure API_KEY before using the API")
    if key is None or not secrets.compare_digest(key.encode(), settings.api_key.encode()):
        raise HTTPException(401, "Chiave di accesso non valida")
