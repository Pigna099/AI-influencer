"""Alerts: deduplicated, actionable warnings tied to domain objects.

Each alert has a stable `key` (so the same condition never appears twice), a
severity, the domain object it belongs to and a short remediation hint.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from .auth import authorize
from .config import settings
from .db import CharacterLora, ExecutionJob, ImageLibrary, Influencer, Session

router = APIRouter(prefix="/api", tags=["Alerts"], dependencies=[Depends(authorize)])


def _alert(key: str, severity: str, object_type: str, object_id: str | None, title: str, remediation: str, since: str | None = None) -> dict:
    return {
        "key": key,
        "severity": severity,
        "object_type": object_type,
        "object_id": object_id,
        "title": title,
        "remediation": remediation,
        "since": since,
    }


@router.get("/alerts")
def list_alerts():
    alerts: dict[str, dict] = {}
    with Session() as db:
        # Failed jobs (one alert per job, latest first).
        failed = db.scalars(
            select(ExecutionJob).where(ExecutionJob.state == "failed").order_by(ExecutionJob.created_at.desc()).limit(20)
        ).all()
        for job in failed:
            info = job.error_info or {}
            alerts[f"job:{job.id}"] = _alert(
                f"job:{job.id}",
                "critical",
                "job",
                job.id,
                info.get("summary") or f"{job.type} job failed",
                info.get("remediation") or "Open the job and retry.",
                job.finished_at.isoformat() if job.finished_at else None,
            )

        # Characters missing policy details.
        characters = db.scalars(select(Influencer)).all()
        for character in characters:
            if character.age is None or not character.synthetic_declared:
                alerts[f"character:{character.id}:policy"] = _alert(
                    f"character:{character.id}:policy",
                    "warning",
                    "character",
                    character.id,
                    f"{character.name}: adult age or synthetic declaration missing",
                    "Open the character editor and complete the policy fields.",
                )
            platforms = (character.platform_policy or {}).get("platforms", {}) or {}
            if any(not (checks or {}).get("ai_disclosure") for checks in platforms.values()):
                alerts[f"character:{character.id}:disclosure"] = _alert(
                    f"character:{character.id}:disclosure",
                    "warning",
                    "character",
                    character.id,
                    f"{character.name}: publishing platform without AI disclosure",
                    "Set the AI disclosure check for every platform in use.",
                )

        # LoRAs whose checkpoint is missing.
        from .integrations.comfyui import checkpoint_meta

        for lora in db.scalars(select(CharacterLora).where(CharacterLora.base_checkpoint.is_not(None))).all():
            meta = checkpoint_meta(lora.base_checkpoint or "")
            if not meta.get("usable"):
                alerts[f"lora:{lora.id}:checkpoint"] = _alert(
                    f"lora:{lora.id}:checkpoint",
                    "critical",
                    "lora",
                    lora.id,
                    f"{lora.name}: base checkpoint not installed",
                    "Install the checkpoint in ComfyUI or pick another one.",
                )

        # Draft assets waiting for review (aggregated per library).
        drafts = db.scalar(
            select(ImageLibrary.id).where(ImageLibrary.status == "draft", ImageLibrary.deleted_at.is_(None)).limit(1)
        )
        if drafts is not None:
            count = len(
                db.scalars(
                    select(ImageLibrary.id).where(
                        ImageLibrary.status == "draft", ImageLibrary.deleted_at.is_(None)
                    ).limit(500)
                ).all()
            )
            alerts["library:drafts"] = _alert(
                "library:drafts",
                "info",
                "library",
                None,
                f"{count} images awaiting review",
                "Open Images -> Review and approve or reject them.",
            )

        # Stale backup.
        backups_dir = settings.media_dir.parent.parent / "backups"
        if not backups_dir.is_dir():
            backups_dir = settings.media_dir.parent / "backups"
        try:
            archives = sorted(
                (path for path in backups_dir.glob("*.tgz") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
            )
            if not archives:
                alerts["backup:missing"] = _alert(
                    "backup:missing", "warning", "system", None, "No backup archive found",
                    "Create a source/database backup in backups/.",
                )
            else:
                from datetime import UTC, datetime, timedelta

                last = archives[-1]
                age = datetime.now(UTC) - datetime.fromtimestamp(last.stat().st_mtime, tz=UTC)
                if age > timedelta(days=14):
                    alerts["backup:stale"] = _alert(
                        "backup:stale",
                        "warning",
                        "system",
                        None,
                        f"Last backup is {age.days} days old",
                        "Create a fresh backup.",
                        datetime.fromtimestamp(last.stat().st_mtime, tz=UTC).isoformat(),
                    )
        except OSError:
            pass

    return {"alerts": list(alerts.values()), "count": len(alerts)}
