from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.modules.organizers.models import OrganizerProfile
from src.app.modules.users.models import User, UserRole


async def get_or_create_organizer_profile(
    db: AsyncSession,
    user: User,
):

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
