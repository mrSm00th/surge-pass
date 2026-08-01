from fastapi import Depends
from typing import Annotated
from src.app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.app.modules.users.models import RefreshToken, OTPVerification, OTPPurpose

import uuid
import random
import string

from datetime import datetime, UTC


async def fetch_refresh_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token_id: uuid.UUID,
):

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == refresh_token_id)
    )

    # handling the case where token is null in the caller func

    return result.scalars().first()


def generate_random_otp(
    length: int = 6,
):

    return "".join(random.SystemRandom().choices(string.digits, k=length))


async def remove_all_valid_otp_for_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    email: str,
    purpose: OTPPurpose,
):
    result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.email == email,
            OTPVerification.purpose == purpose,
            OTPVerification.is_used.is_(False),
            OTPVerification.expires_at > datetime.now(UTC),
        )
    )

    valid_otps = result.scalars().all()

    for otp in valid_otps:
        await db.delete(otp)

    await db.commit()


async def get_latest_valid_otp(
    db: Annotated[AsyncSession, Depends(get_db)],
    email: str,
    purpose: OTPPurpose,
):

    result = await db.execute(
        select(OTPVerification)
        .where(
            OTPVerification.email == email,
            OTPVerification.is_used.is_(False),
            OTPVerification.purpose == purpose,
            OTPVerification.expires_at > datetime.now(UTC),
        )
        .order_by(OTPVerification.created_at.desc())
    )

    return result.scalars().first()
