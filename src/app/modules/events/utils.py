import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.modules.events.models import Event


async def fetch_event_by_id(
    db: AsyncSession,
    event_id: uuid.UUID,
):

    result = await db.execute(select(Event).where(Event.id == event_id))

    event = result.scalars().first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found with specified ID",
        )

    return event
