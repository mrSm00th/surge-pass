from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.db.database import get_db
from src.app.modules.organizers.models import KYCStatus, OrganizerProfile
from src.app.modules.users.models import User, UserRole


async def get_or_create_organizer_profile(
    db: AsyncSession,
    user: User,
) -> OrganizerProfile:

    if user.role == UserRole.ORGANIZER:
        result = await db.execute(
            select(OrganizerProfile).where(OrganizerProfile.user_id == user.id)
        )

        organizer_profile = result.scalars().first()

        if not organizer_profile:
            raise ValueError(
                f"Organizer profile not found for user {user.id} with role ORGANIZER"
            )

        return organizer_profile

    user.role = UserRole.ORGANIZER
    db.add(user)

    organizer = OrganizerProfile(user_id=user.id)
    db.add(organizer)

    await db.flush()
    return organizer


async def get_organizer_profile_by_user_id(
    db: AsyncSession,
    user_id: str,
) -> OrganizerProfile:

    result = await db.execute(
        select(OrganizerProfile).where(OrganizerProfile.user_id == user_id)
    )

    organizer_profile = result.scalars().first()

    if not organizer_profile:
        raise ValueError(
            f"Organizer profile not found for user {user_id} with role ORGANIZER"
        )

    return organizer_profile


async def get_current_organizer(
    current_user: Annotated[User, Depends(require_roles(UserRole.ORGANIZER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizerProfile:
    result = await db.execute(
        select(OrganizerProfile).where(OrganizerProfile.user_id == current_user.id)
    )
    organizer = result.scalars().first()

    if not organizer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organizer profile not found for user with ORGANIZER role.",
        )
    return organizer


async def get_verified_organizer(
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
) -> OrganizerProfile:
    if organizer.kyc_status != KYCStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete KYC verification before performing this action.",
        )
    return organizer
