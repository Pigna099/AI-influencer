"""Realistic reply scheduling: random delays, activity hours and due delivery.

The scheduler loop runs inside the API process (see main.py lifespan) and calls the
existing run_turn to generate and store due replies.
"""

import asyncio
import logging
import random
import threading
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select

from .config import settings
from .db import Conversation, Influencer, ScheduledReply, Session, now

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_SECONDS = 20


def hour_in_window(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def next_window_start(local: datetime, character, days: set[int]) -> datetime:
    for offset in range(8):
        day = (local + timedelta(days=offset)).date()
        if day.weekday() not in days:
            continue
        start = datetime.combine(day, time(hour=character.activity_start_hour), tzinfo=local.tzinfo)
        if start > local:
            return start
    return local + timedelta(days=1)


def compute_deliver_at(character, *, now_utc: datetime | None = None, rng=random, tz=None, delay_seconds=None) -> datetime:
    """Random delay, pushed to the next activity window when the character sleeps."""
    now_utc = now_utc or datetime.now(UTC)
    if delay_seconds is None:
        low = max(0, int(character.reply_delay_min_seconds or 0))
        high = max(low, int(character.reply_delay_max_seconds or 0))
        delay = rng.uniform(low, high) if high > low else float(low)
    else:
        delay = max(0.0, float(delay_seconds))
    candidate = now_utc + timedelta(seconds=delay)
    if not character.activity_enabled:
        return candidate
    days = {int(day) for day in (character.activity_days or []) if 0 <= int(day) <= 6}
    if not days:
        days = set(range(7))
    timezone = tz or datetime.now().astimezone().tzinfo
    local = candidate.astimezone(timezone)
    for _ in range(8):
        if local.weekday() in days and hour_in_window(
            local.hour, character.activity_start_hour, character.activity_end_hour
        ):
            return local.astimezone(UTC)
        local = next_window_start(local, character, days)
    return candidate


def pending_for_conversation(db, conversation_id: str) -> tuple[int, datetime | None]:
    count, deliver_at = db.execute(
        select(func.count(), func.min(ScheduledReply.deliver_at)).where(
            ScheduledReply.conversation_id == conversation_id,
            ScheduledReply.status == "scheduled",
        )
    ).one()
    return int(count or 0), deliver_at


def schedule_reply(
    conversation_id: str,
    content: str | None,
    kind: str = "reply",
    absence_hours: int = 48,
    source_message_id: str | None = None,
    delay_seconds: float | None = None,
) -> ScheduledReply:
    with Session.begin() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("Conversazione non trovata")
        character = db.get(Influencer, conversation.character_id)
        item = ScheduledReply(
            conversation_id=conversation_id,
            character_id=conversation.character_id,
            kind=kind,
            content=content,
            absence_hours=absence_hours,
            deliver_at=compute_deliver_at(character, delay_seconds=delay_seconds),
            status="scheduled",
            source_message_id=source_message_id,
        )
        db.add(item)
        conversation.updated_at = now()
        db.flush()
        return item


def maybe_schedule_proactive(conversation_id: str) -> ScheduledReply | None:
    """Human mode: queue a spontaneous follow-up when none is already pending."""
    if not settings.human_mode_proactive_enabled:
        return None
    low = max(1, settings.human_mode_proactive_min_minutes)
    high = max(low, settings.human_mode_proactive_max_minutes)
    with Session() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or not conversation.human_mode:
            return None
        pending, _ = pending_for_conversation(db, conversation_id)
        if pending > 0:
            return None
    delay = random.uniform(low * 60, high * 60)
    return schedule_reply(conversation_id, content=None, kind="proactive", delay_seconds=delay)


def deliver_due_replies(limit: int = 5) -> int:
    with Session() as db:
        ids = list(
            db.scalars(
                select(ScheduledReply.id)
                .where(ScheduledReply.status == "scheduled", ScheduledReply.deliver_at <= now())
                .order_by(ScheduledReply.deliver_at)
                .limit(limit)
            )
        )
    delivered = 0
    for reply_id in ids:
        if deliver_reply(reply_id):
            delivered += 1
    return delivered


def deliver_reply(reply_id: str) -> bool:
    from fastapi import HTTPException

    from .characters import run_turn

    with Session() as db:
        item = db.get(ScheduledReply, reply_id)
        if item is None or item.status != "scheduled":
            return False
        conversation_id = item.conversation_id
        content = item.content
        kind = item.kind
        absence_hours = item.absence_hours
        source_message_id = item.source_message_id
    try:
        message = run_turn(
            conversation_id, content=content, kind=kind, absence_hours=absence_hours, store_user=False
        )
        with Session.begin() as db:
            item = db.get(ScheduledReply, reply_id)
            if item is not None:
                item.status = "sent"
                item.message_id = message.get("id") if isinstance(message, dict) else None
                item.sent_at = now()
                item.error = None
        if content is not None and source_message_id:
            _extract_memories_async(conversation_id, source_message_id)
        if content is not None:
            maybe_schedule_proactive(conversation_id)
        return True
    except HTTPException as error:
        with Session.begin() as db:
            item = db.get(ScheduledReply, reply_id)
            if item is None:
                return False
            item.attempts = (item.attempts or 0) + 1
            item.error = str(error.detail)[:500]
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
            else:
                item.deliver_at = now() + timedelta(seconds=RETRY_SECONDS)
        return False
    except Exception as error:
        logger.exception("Scheduled reply %s failed", reply_id)
        with Session.begin() as db:
            item = db.get(ScheduledReply, reply_id)
            if item is not None:
                item.attempts = (item.attempts or 0) + 1
                item.error = str(error)[:500]
                item.status = "failed"
        return False


def _extract_memories_async(conversation_id: str, source_message_id: str) -> None:
    from .chat_service import extract_memories

    def worker():
        try:
            extract_memories(conversation_id, source_message_id)
        except Exception:
            logger.exception("Memory extraction after scheduled reply failed")

    threading.Thread(target=worker, daemon=True).start()


async def scheduler_loop() -> None:
    logger.info("Reply scheduler started (poll %ss)", settings.scheduler_poll_seconds)
    while True:
        try:
            await asyncio.to_thread(deliver_due_replies)
        except Exception:
            logger.exception("Scheduler loop error")
        await asyncio.sleep(max(1, settings.scheduler_poll_seconds))
