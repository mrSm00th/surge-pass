import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.db.database import get_db
from src.app.modules.events.models import Event, EventStatus
from src.app.modules.events.schemas import EventCreate, EventOut, EventUpdate
from src.app.modules.events.utils import fetch_event_by_id
from src.app.modules.organizers.models import OrganizerProfile
from src.app.modules.organizers.utils import (
    get_current_organizer,
    get_or_create_organizer_profile,
    get_verified_organizer,
)
from src.app.modules.tickets.models import TicketTier
from src.app.modules.users.models import User, UserRole

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EventOut,
)
async def create_event(
    data: EventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.ORGANIZER))
    ],
):

    try:
        organizer = await get_or_create_organizer_profile(db, current_user)

        new_event = Event(
            organizer_id=organizer.id,
            title=data.title,
            description=data.description if data.description else None,
            venue_name=data.venue_name,
            venue_address=data.venue_address,
            city=data.city,
            status=EventStatus.DRAFT,
            event_start_time=data.event_start_time,
            event_end_time=data.event_end_time,
            sale_start_at=data.sale_start_at,
            sale_end_at=data.sale_end_at,
            max_tickets_per_user=data.max_tickets_per_user,
        )

        db.add(new_event)
        await db.commit()

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This request conflicts with existing data.",
        )

    await db.refresh(new_event)
    return new_event


@router.post(
    "/{event_id}/publish",
    status_code=status.HTTP_200_OK,
    response_model=EventOut,
)
async def publish_event(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: str,
    organizer: Annotated[OrganizerProfile, Depends(get_verified_organizer)],
):

    event = await fetch_event_by_id(db, event_id)

    if event.organizer_id != organizer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found for this user",
        )

    if event.status in (
        EventStatus.PUBLISHED,
        EventStatus.CANCELLED,
        EventStatus.COMPLETED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event can't be published as its either already published, cancelled or completed",
        )

    now = datetime.now(UTC)

    if event.event_start_time < now or event.sale_start_at < now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event can't be published as its either already past its sale start time or already past its start time.",
        )

    tier_count = await db.scalar(
        select(func.count())
        .select_from(TicketTier)
        .where(TicketTier.event_id == event.id)
    )

    if not tier_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot publish an event with no ticket tiers.",
        )
    event.status = EventStatus.PUBLISHED

    await db.commit()

    await db.refresh(event)

    return event


# allowing an organizer with pending kyc to update the draf event
@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await fetch_event_by_id(db, event_id)
    if event.organizer_id != organizer.id:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status != EventStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Only draft events can be edited.",
        )

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    for field, value in update_data.items():
        setattr(event, field, value)

    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await fetch_event_by_id(db, event_id)

    if event.organizer_id != organizer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
        )

    if event.status != EventStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft events can be deleted. Cancel a published event instead.",
        )

    await db.delete(event)
    await db.commit()
