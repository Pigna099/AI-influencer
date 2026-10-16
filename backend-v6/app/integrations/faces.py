"""Local face embeddings (insightface buffalo_l) for identity similarity scoring.

Runs entirely on the local machine (CPU); embeddings never leave the system.
When the model or package is unavailable the helpers return None so callers can
degrade gracefully.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path

from PIL import Image

from ..config import settings

logger = logging.getLogger(__name__)

_app = None
_load_failed = False


def _get_app():
    global _app, _load_failed
    if _app is not None or _load_failed or not settings.face_similarity_enabled:
        return _app
    try:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name=settings.face_model,
            root=str(settings.insightface_home),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _app = app
    except Exception as error:  # noqa: BLE001 - missing model/package must not break the API
        logger.warning("insightface unavailable: %s", error)
        _load_failed = True
    return _app


def embedding_for(data: bytes) -> list[float] | None:
    """Embedding of the largest face in the image, or None when no face is found."""
    app = _get_app()
    if app is None:
        return None
    try:
        import numpy as np

        with Image.open(io.BytesIO(data)) as image:
            array = np.asarray(image.convert("RGB"))
        faces = app.get(array)
    except Exception as error:  # noqa: BLE001
        logger.info("face embedding failed: %s", error)
        return None
    if not faces:
        return None
    face = max(faces, key=lambda item: (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]))
    vector = getattr(face, "normed_embedding", None)
    if vector is None:
        return None
    return [float(value) for value in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def similarity_percent(reference: list[float] | None, candidate: list[float] | None) -> float | None:
    """Face similarity in 0-100 (cosine), or None when embeddings are unavailable."""
    if reference is None or candidate is None:
        return None
    return round(cosine_similarity(reference, candidate) * 100, 1)


def embedding_for_path(path: Path) -> list[float] | None:
    try:
        return embedding_for(path.read_bytes())
    except OSError:
        return None
