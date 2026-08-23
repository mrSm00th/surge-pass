import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.modules.events.models import Event, EventStatus


def _queue_key(event_id: uuid.UUID) -> str:
    return f"waiting_room:queue:{event_id}"


def _admitted_key(event_id: uuid.UUID, ticket_id: str) -> str:
    return f"waiting_room:admitted:{event_id}:{ticket_id}"


async def join_queue(redis: Redis, event: Event, existing_ticket_id: str | None) -> str:

    if existing_ticket_id:
        already_queued = await redis.zscore(_queue_key(event.id), existing_ticket_id)
        already_admitted = await redis.get(_admitted_key(event.id, existing_ticket_id))
        if already_queued is not None or already_admitted:
            return existing_ticket_id

    ticket_id = str(uuid.uuid4())
    await redis.zadd(_queue_key(event.id), {ticket_id: time.time()})
    return ticket_id


async def get_status(redis: Redis, event: Event, ticket_id: str) -> dict:
    now = datetime.now(timezone.utc)

    if now < event.sale_start_at:
        opens_in = int((event.sale_start_at - now).total_seconds())
        return {"admitted": False, "sale_started": False, "opens_in_seconds": opens_in}

    token = await redis.get(_admitted_key(event.id, ticket_id))
    if token:
        return {"admitted": True, "sale_started": True, "access_token": token}

    rank = await redis.zrank(_queue_key(event.id), ticket_id)
    if rank is None:
        # not an error- likely an error that either the ticket expired or user never joined
        return {"admitted": False, "sale_started": True}

    total = await redis.zcard(_queue_key(event.id))
    est_seconds = (
        rank // settings.waiting_room_admission_batch_size
    ) * settings.waiting_room_admission_interval_seconds

    return {
        "admitted": False,
        "sale_started": True,
        "position": rank + 1,
        "total_waiting": total,
        "estimated_wait_seconds": est_seconds,
    }


def _issue_access_token(event_id: uuid.UUID, ticket_id: str) -> str:
    return jwt.encode(
        {
            "typ": "waiting_room_access",  # distinguishes this from a login/session token signed with the same key
            "event_id": str(event_id),
            "ticket_id": ticket_id,
            "exp": datetime.now(timezone.utc)
            + timedelta(seconds=settings.waiting_room_token_ttl_seconds),
        },
        settings.access_token_secret_key.get_secret_value(),
        algorithm=settings.access_token_signing_algorithm,
    )


async def run_admission_tick(redis: Redis, db: AsyncSession) -> None:

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Event).where(
            Event.status == EventStatus.PUBLISHED, Event.sale_start_at <= now
        )
    )
    open_events = result.scalars().all()

    for event in open_events:
        key = _queue_key(event.id)
        if await redis.zcard(key) == 0:
            continue

        admitted = await redis.zpopmin(key, settings.waiting_room_admission_batch_size)
        for ticket_id, _score in admitted:
            token = _issue_access_token(event.id, ticket_id)
            await redis.set(
                _admitted_key(event.id, ticket_id),
                token,
                ex=settings.waiting_room_token_ttl_seconds,
            )
