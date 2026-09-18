"""Generation presets: reusable image settings saved from the image playground."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select

from .auth import authorize
from .char_schemas import StrictModel
from .db import GenerationPreset, Session, now

router = APIRouter(prefix="/api", tags=["Presets"], dependencies=[Depends(authorize)])


class PresetInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)


class PresetPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    payload: dict | None = None


def preset_out(item: GenerationPreset) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "payload": item.payload or {},
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/presets")
def list_presets(limit: int = Query(100, ge=1, le=300)):
    with Session() as db:
        items = db.scalars(select(GenerationPreset).order_by(GenerationPreset.name).limit(limit))
        return [preset_out(item) for item in items]


@router.post("/presets", status_code=201)
def create_preset(body: PresetInput):
    with Session.begin() as db:
        item = GenerationPreset(name=body.name, payload=body.payload)
        db.add(item)
        db.flush()
    return preset_out(item)


@router.patch("/presets/{preset_id}")
def patch_preset(preset_id: str, body: PresetPatch):
    with Session.begin() as db:
        item = db.get(GenerationPreset, preset_id)
        if item is None:
            raise HTTPException(404, "Elemento non trovato")
        if body.name is not None:
            item.name = body.name
        if body.payload is not None:
            item.payload = body.payload
        item.updated_at = now()
        db.flush()
        return preset_out(item)


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str):
    with Session.begin() as db:
        item = db.get(GenerationPreset, preset_id)
        if item is None:
            raise HTTPException(404, "Elemento non trovato")
        db.delete(item)
    return {"deleted": True, "id": preset_id}
