from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import CurrentUser
from src.app.db.database import get_db
from src.app.modules.organizers.models import KYCStatus, OrganizerProfile
from src.app.modules.users.models import User, UserRole


def require_roles(*allowed_roles: UserRole):

    def role_checker(current_user: CurrentUser) -> User:

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your account to access this resource.",
            )
        return current_user

    return role_checker


def inject_organizer():

    async def fetch_organizer(
        db: Annotated[AsyncSession, Depends(get_db)],
    ):

        user = require_roles(UserRole.ORGANIZER)

        result = await db.execute(
            select(OrganizerProfile).where(OrganizerProfile.user_id == user.id)
        )

        organizer = result.scalars().first()

        if not organizer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organizer Profile not found",
            )

        if not organizer.kyc_status == KYCStatus.VERIFIED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your organizer profile by completing the kyc verification ",
            )

        return organizer
