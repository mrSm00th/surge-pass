import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import fakeredis
import pytest

from src.app.modules.events.models import Event, EventStatus
from src.app.modules.waiting_rooms.services import run_admission_tick

pytestmark = pytest.mark.anyio


def _make_event() -> Event:
    return Event(
        id=uuid.uuid4(),
        status=EventStatus.PUBLISHED,
        sale_start_at=datetime.now(UTC) - timedelta(minutes=1),
    )


def _fake_db_returning(events: list[Event]):

    class _FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return _FakeScalars(self._items)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeResult(events))
    return db


@pytest.fixture
async def redis():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server
    await server.aclose()


async def test_single_tick_admits_only_up_to_batch_size(redis):
    event = _make_event()
    queue_key = f"waiting_room:queue:{event.id}"

    for i in range(10):
        await redis.zadd(queue_key, {f"ticket-{i}": i})

    db = _fake_db_returning([event])

    await run_admission_tick(redis, db)

    remaining = await redis.zcard(queue_key)
    admitted_keys = await redis.keys(f"waiting_room:admitted:{event.id}:*")

    assert remaining == 5
    assert len(admitted_keys) == 5


async def test_two_concurrent_ticks_for_the_same_event_only_admit_one_batch(redis):

    event = _make_event()
    queue_key = f"waiting_room:queue:{event.id}"

    for i in range(10):
        await redis.zadd(queue_key, {f"ticket-{i}": i})

    db_a = _fake_db_returning([event])
    db_b = _fake_db_returning([event])

    await asyncio.gather(
        run_admission_tick(redis, db_a),
        run_admission_tick(redis, db_b),
    )

    remaining = await redis.zcard(queue_key)
    admitted_keys = await redis.keys(f"waiting_room:admitted:{event.id}:*")

    assert remaining == 5
    assert len(admitted_keys) == 5


async def test_second_worker_skips_a_locked_event_without_erroring(redis):
    event = _make_event()
    queue_key = f"waiting_room:queue:{event.id}"
    await redis.zadd(queue_key, {"ticket-1": 1})

    lock_key = f"waiting_room:admission_lock:{event.id}"
    await redis.set(lock_key, "1", nx=True, ex=30)

    db = _fake_db_returning([event])

    await run_admission_tick(redis, db)

    assert await redis.zcard(queue_key) == 1
    assert len(await redis.keys(f"waiting_room:admitted:{event.id}:*")) == 0


async def test_empty_queue_is_skipped_without_taking_the_lock(redis):
    event = _make_event()
    db = _fake_db_returning([event])

    await run_admission_tick(redis, db)

    lock_key = f"waiting_room:admission_lock:{event.id}"

    assert await redis.get(lock_key) is None
