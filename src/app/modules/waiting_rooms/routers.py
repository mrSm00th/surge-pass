import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.redis import get_redis
from src.app.db.database import get_db
from src.app.modules.events.models import Event, EventStatus
from src.app.modules.waiting_rooms import schemas, service

router = APIRouter(prefix="/waiting-room", tags=["waiting-room"])


def _cookie_name(event_id: uuid.UUID) -> str:

    return f"ticket_id:{event_id}"


async def _get_published_event(event_id: uuid.UUID, db: AsyncSession) -> Event:
    event = await db.get(Event, event_id)
    if not event or event.status != EventStatus.PUBLISHED:
        raise HTTPException(404, "Event not found")
    return event


@router.post("/{event_id}/join", response_model=schemas.JoinQueueResponse)
async def join(
    event_id: uuid.UUID,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)
    existing_ticket = request.cookies.get(_cookie_name(event_id))

    ticket_id = await service.join_queue(redis, event, existing_ticket)
    response.set_cookie(_cookie_name(event_id), ticket_id, httponly=True, max_age=3600)
    return schemas.JoinQueueResponse(ticket_id=ticket_id)


@router.get("/{event_id}/status", response_model=schemas.QueueStatusResponse)
async def status(
    event_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    event = await _get_published_event(event_id, db)
    ticket_id = request.cookies.get(_cookie_name(event_id))
    if not ticket_id:
        raise HTTPException(400, "No ticket found — join the queue first")

    result = await service.get_status(redis, event, ticket_id)
    return schemas.QueueStatusResponse(**result)
