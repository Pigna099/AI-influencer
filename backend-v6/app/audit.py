"""Lightweight audit log: approvals, overrides, publication, deletion, activation."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from .auth import authorize
from .db import AuditEvent, Session, identifier, now

router = APIRouter(prefix="/api", tags=["Audit"], dependencies=[Depends(authorize)])


def record(db, action: str, object_type: str, object_id: str | None = None, **detail) -> None:
    """Append an audit event to the current transaction (best effort)."""
    db.add(
        AuditEvent(
            id=identifier(),
            action=action,
            object_type=object_type,
            object_id=object_id,
            detail={key: value for key, value in detail.items() if value is not None},
            created_at=now(),
        )
    )


def event_out(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "detail": event.detail or {},
        "created_at": event.created_at.isoformat(),
    }


@router.get("/audit")
def list_audit(
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        query = select(AuditEvent).order_by(AuditEvent.created_at.desc())
        if action:
            query = query.where(AuditEvent.action == action)
        if object_type:
            query = query.where(AuditEvent.object_type == object_type)
        if object_id:
            query = query.where(AuditEvent.object_id == object_id)
        events = db.scalars(query.limit(limit).offset(offset)).all()
        return [event_out(event) for event in events]
