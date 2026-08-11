import asyncio
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.core.razorpay_client import razorpay_client
from src.app.db.database import get_db
from src.app.modules.organizers.models import KYCStatus, OrganizerProfile
from src.app.modules.organizers.schemas import RazorpayLinkedAccountCreaterequest
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


async def create_razorpay_account(
    organizer: OrganizerProfile,
    payload: RazorpayLinkedAccountCreaterequest,
):

    try:
        new_razorpay_account = await asyncio.to_thread(
            razorpay_client.account.create,
            {
                "email": payload.contact_email,
                "phone": payload.contact_phone,
                "type": "route",
                "reference_id": str(organizer.id),
                "legal_business_name": payload.legal_business_name,
                "business_type": str,
                "contact_name": payload.stakeholder.name,
                "profile": {
                    "category": "event_management",
                    "subcategory": "event_management_services",
                    "addresses": {
                        "registered": {
                            "street1": payload.stakeholder.address.street,
                            "city": payload.stakeholder.address.city,
                            "state": payload.stakeholder.address.state,
                            "postal_code": payload.stakeholder.address.postal_code,
                            "country": payload.stakeholder.address.country,
                        }
                    },
                },
            },
        )

    except Exception:
        raise ValueError("something went wrong, check your request and try again")

    return new_razorpay_account


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
