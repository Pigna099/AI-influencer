import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from .config import settings

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Failed-attempt limiter: protects the API key from brute force on a shared LAN.
MAX_FAILURES = 30
WINDOW_SECONDS = 60
BLOCK_SECONDS = 300

_failures: dict[str, deque[float]] = defaultdict(deque)
_blocked_until: dict[str, float] = {}


def reset_limits() -> None:
    _failures.clear()
    _blocked_until.clear()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_blocked(ip: str) -> None:
    until = _blocked_until.get(ip, 0)
    if until > time.time():
        raise HTTPException(429, "Too many failed attempts: try again later")


def _record_failure(ip: str) -> None:
    moment = time.time()
    window = _failures[ip]
    window.append(moment)
    while window and moment - window[0] > WINDOW_SECONDS:
        window.popleft()
    if len(window) > MAX_FAILURES:
        _blocked_until[ip] = moment + BLOCK_SECONDS
        window.clear()


def _matches(key: str, expected: str) -> bool:
    return bool(expected) and secrets.compare_digest(key.encode(), expected.encode())


def authorize(request: Request, key: str | None = Depends(key_header)):
    if not settings.api_key:
        raise HTTPException(503, "Configure API_KEY before using the API")
    ip = _client_ip(request)
    _check_blocked(ip)
    # Rotation: API_KEY_PREVIOUS keeps working while clients migrate to the new key.
    if key is None or not (_matches(key, settings.api_key) or _matches(key, settings.api_key_previous)):
        _record_failure(ip)
        raise HTTPException(401, "Invalid access key")
    _failures.pop(ip, None)
    _blocked_until.pop(ip, None)
