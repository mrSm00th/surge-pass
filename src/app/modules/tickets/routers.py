import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.core.redis import get_redis
from src.app.db.database import get_db
from src.app.modules.events.models import EventStatus
from src.app.modules.events.utils import fetch_event_by_id
from src.app.modules.organizers.utils import get_organizer_profile_by_user_id
from src.app.modules.tickets.models import TicketTier
from src.app.modules.tickets.schemas import (
    BuyTicketRequest,
    BuyTicketResponse,
    CreateTicketTier,
    TicketTierOut,
)
from src.app.modules.users.models import User, UserRole
from src.app.modules.waiting_rooms.dependencies import require_waiting_room_access
from src.app.modules.waiting_rooms.services import use_admission_token

router = APIRouter(prefix="/api/events", tags=["Tickets"])


@router.post(
    "/{event_id}/tiers",
    status_code=status.HTTP_201_CREATED,
    response_model=TicketTierOut,
)
async def create_ticket_tier(
    event_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ORGANIZER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: CreateTicketTier,
):

    event = await fetch_event_by_id(db, event_id)
    organizer = await get_organizer_profile_by_user_id(db, current_user.id)

    # retruning a naive error for security purpose
    if event.organizer_id != organizer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    if event.status not in (EventStatus.DRAFT, EventStatus.PUBLISHED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only create ticket tiers for events that are in DRAFT or PUBLISHED status",
        )

    now = datetime.now(UTC)

    if event.sale_start_at < now or event.event_start_time < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cant create new ticket tiers for events that are either already on sale or have already started",
        )

    new_ticket_tier = TicketTier(
        event_id=event.id,
        name=data.name,
        description=data.description,
        total_capacity=data.total_capacity,
        price=data.price,
    )

    db.add(new_ticket_tier)

    try:
        await db.commit()

    except IntegrityError:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The current request is conflicting with existing data."
            "Please check your request and try again.",
        )

    await db.refresh(new_ticket_tier)
    return new_ticket_tier


@router.post(
    "/{event_id}/tiers/{tier_id}/reserve",
    status_code=status.HTTP_200_OK,
    response_model=BuyTicketResponse,
)
async def buy_ticket(
    event_id: uuid.UUID,
    tier_id: uuid.UUID,
    data: BuyTicketRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
    waiting_room_access: Annotated[dict, Depends(require_waiting_room_access)],
):
    ticket_id_from_token = waiting_room_access["ticket_id"]
    old_token = await use_admission_token(redis, event_id, ticket_id_from_token)

    if old_token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This waiting room admission has already been used or has expired",
        )

    update_query = (
        update(TicketTier)
        .where(TicketTier.id == tier_id)
        .where(TicketTier.event_id == event_id)
        .where(TicketTier.sold_count + data.quantity <= TicketTier.total_capacity)
        .values(sold_count=TicketTier.sold_count + data.quantity)
        .returning(TicketTier.price)
    )

    result = await db.execute(update_query)
    updated_row = result.first()

    if updated_row is None:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Not enough tickets available in this tier",
        )

    tier_price = updated_row[0]
    await db.commit()

    total_price = tier_price * data.quantity

    return BuyTicketResponse(
        ticket_tier_id=tier_id,
        quantity=data.quantity,
        total_price=total_price,
    )
