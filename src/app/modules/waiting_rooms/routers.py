import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.redis import get_redis
from src.app.db.database import get_db
from src.app.modules.events.models import Event, EventStatus
from src.app.modules.waiting_rooms.schemas import JoinQueueResponse, QueueStatusResponse
from src.app.modules.waiting_rooms.services import get_status, join_queue

router = APIRouter(prefix="/waiting-room", tags=["waiting-room"])


def _cookie_name(event_id: uuid.UUID) -> str:

    return f"ticket_id:{event_id}"


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
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)

    cookie_name = _cookie_name(event_id)
    existing_ticket = request.cookies.get(cookie_name)

    ticket_id = await join_queue(redis, event, existing_ticket)

    # allowing a max age of 1 hr
    response.set_cookie(cookie_name, ticket_id, httponly=True, max_age=3600)

    return JoinQueueResponse(ticket_id=ticket_id)


@router.get("/{event_id}/status", response_model=QueueStatusResponse)
async def queue_status(
    event_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)

    ticket_id = request.cookies.get(_cookie_name(event_id))
    if not ticket_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ticket found — join the queue first",
        )

    result = await get_status(redis, event, ticket_id)
    return QueueStatusResponse(**result)
