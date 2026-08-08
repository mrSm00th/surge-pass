from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.db.database import get_db
from src.app.modules.events.models import Event, EventStatus
from src.app.modules.events.schemas import EventCreate
from src.app.modules.organizers.utils import get_or_create_organizer_profile
from src.app.modules.users.models import User, UserRole

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
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
