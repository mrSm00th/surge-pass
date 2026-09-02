import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import CurrentUser
from src.app.core.config import settings
from src.app.core.redis import get_redis
from src.app.db.database import get_db
from src.app.modules.events.models import Event, EventStatus
from src.app.modules.waiting_rooms.schemas import JoinQueueResponse, QueueStatusResponse
from src.app.modules.waiting_rooms.services import (
    get_status,
    get_ticket_id_for_user,
    join_queue,
)

router = APIRouter(prefix="/waiting-room", tags=["waiting-room"])


async def _get_published_event(
    event_id: uuid.UUID,
    db: AsyncSession,
) -> Event:

    event = await db.get(Event, event_id)

    if not event or event.status != EventStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
        )

    return event


@router.post(
    "/{event_id}/join",
    response_model=JoinQueueResponse,
)
async def join(
    event_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)

    ticket_id = await join_queue(redis, event, current_user.id)

    return JoinQueueResponse(ticket_id=ticket_id)


@router.get("/{event_id}/status", response_model=QueueStatusResponse)
async def queue_status(
    event_id: uuid.UUID,
    current_user: CurrentUser,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)

    ticket_id = await get_ticket_id_for_user(redis, event_id, current_user.id)
    if not ticket_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ticket found — join the queue first",
        )

    result = await get_status(redis, event, ticket_id)

    access_token = result.pop("access_token", None)
    if access_token:
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            max_age=settings.waiting_room_token_ttl_seconds,
        )

    return QueueStatusResponse(**result)
