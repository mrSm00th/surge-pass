import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest

from src.app.modules.events.models import Event, EventStatus
from src.app.modules.waiting_rooms.services import get_ticket_id_for_user, join_queue

pytestmark = pytest.mark.anyio


def _make_event() -> Event:
    return Event(
        id=uuid.uuid4(),
        status=EventStatus.PUBLISHED,
        sale_start_at=datetime.now(UTC) - timedelta(minutes=1),
    )


@pytest.fixture
async def redis():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server
    await server.aclose()


async def test_first_join_creates_a_ticket_and_queues_it(redis):
    event = _make_event()
    user_id = uuid.uuid4()

    ticket_id = await join_queue(redis, event, user_id)

    assert ticket_id is not None
    assert await redis.zcard(f"waiting_room:queue:{event.id}") == 1
    assert await get_ticket_id_for_user(redis, event.id, user_id) == ticket_id


async def test_rejoining_returns_the_same_ticket_and_does_not_duplicate(redis):
    event = _make_event()
    user_id = uuid.uuid4()

    first_ticket = await join_queue(redis, event, user_id)
    second_ticket = await join_queue(redis, event, user_id)

    assert first_ticket == second_ticket
    # one user, one queue slot — regardless of how many times they "join"
    assert await redis.zcard(f"waiting_room:queue:{event.id}") == 1


async def test_concurrent_joins_from_the_same_user_do_not_create_two_tickets(redis):

    event = _make_event()
    user_id = uuid.uuid4()

    first_ticket, second_ticket = await asyncio.gather(
        join_queue(redis, event, user_id),
        join_queue(redis, event, user_id),
    )

    assert first_ticket == second_ticket
    assert await redis.zcard(f"waiting_room:queue:{event.id}") == 1


async def test_two_different_users_get_two_separate_tickets(redis):
    event = _make_event()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    ticket_a = await join_queue(redis, event, user_a)
    ticket_b = await join_queue(redis, event, user_b)

    assert ticket_a != ticket_b
    assert await redis.zcard(f"waiting_room:queue:{event.id}") == 2


async def test_ticket_lookup_returns_none_before_joining(redis):
    event = _make_event()
    user_id = uuid.uuid4()

    assert await get_ticket_id_for_user(redis, event.id, user_id) is None
