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


def _user_ticket_key(event_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"waiting_room:user:{event_id}:{user_id}"


def _admission_lock_key(event_id: uuid.UUID) -> str:
    return f"waiting_room:admission_lock:{event_id}"


async def join_queue(redis: Redis, event: Event, user_id: uuid.UUID) -> str:
    user_key = _user_ticket_key(event.id, user_id)
    new_ticket_id = str(uuid.uuid4())

    claimed = await redis.set(user_key, new_ticket_id, nx=True)

    if not claimed:
        return await redis.get(user_key)

    await redis.zadd(_queue_key(event.id), {new_ticket_id: time.time()})
    return new_ticket_id


async def get_ticket_id_for_user(
    redis: Redis, event_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    return await redis.get(_user_ticket_key(event_id, user_id))


async def get_status(redis: Redis, event: Event, ticket_id: str) -> dict:
    now = datetime.now(timezone.utc)

    if now < event.sale_start_at:
        seconds_until_open = int((event.sale_start_at - now).total_seconds())
        return {
            "admitted": False,
            "sale_started": False,
            "opens_in_seconds": seconds_until_open,
        }

    admission_token = await redis.get(_admitted_key(event.id, ticket_id))
    if admission_token:
        return {
            "admitted": True,
            "sale_started": True,
            "access_token": admission_token,
        }

    position_in_queue = await redis.zrank(_queue_key(event.id), ticket_id)

    if position_in_queue is None:
        return {"admitted": False, "sale_started": True}

    return {
        "admitted": False,
        "sale_started": True,
        "position": position_in_queue + 1,
    }


def _issue_access_token(event_id: uuid.UUID, ticket_id: str) -> str:
    payload = {
        "typ": "waiting_room_access",
        "event_id": str(event_id),
        "ticket_id": ticket_id,
        "exp": datetime.now(timezone.utc)
        + timedelta(seconds=settings.waiting_room_token_ttl_seconds),
    }

    return jwt.encode(
        payload,
        settings.waiting_room_token_secret_key.get_secret_value(),
        algorithm=settings.access_token_signing_algorithm,
    )


async def run_admission_tick(redis: Redis, db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)

    query = select(Event).where(
        Event.status == EventStatus.PUBLISHED,
        Event.sale_start_at <= now,
    )
    result = await db.execute(query)
    events_on_sale = result.scalars().all()

    for event in events_on_sale:
        queue_key = _queue_key(event.id)

        people_waiting = await redis.zcard(queue_key)
        if people_waiting == 0:
            continue

        lock_key = _admission_lock_key(event.id)
        lock_ttl_seconds = settings.waiting_room_admission_interval_seconds * 3
        acquired_lock = await redis.set(lock_key, "1", nx=True, ex=lock_ttl_seconds)

        if not acquired_lock:
            continue

        people_to_admit = await redis.zpopmin(
            queue_key, settings.waiting_room_admission_batch_size
        )

        for ticket_id, _join_timestamp in people_to_admit:
            token = _issue_access_token(event.id, ticket_id)

            await redis.set(
                _admitted_key(event.id, ticket_id),
                token,
                ex=settings.waiting_room_token_ttl_seconds,
            )


async def use_admission_token(
    redis: Redis, event_id: uuid.UUID, ticket_id: str
) -> str | None:
    return await redis.getdel(_admitted_key(event_id, ticket_id))
