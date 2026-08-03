from fastapi import Depends
from typing import Annotated
from src.app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from src.app.modules.users.models import RefreshToken, OTPVerification, OTPPurpose, User

import uuid
import random
import string

from datetime import datetime, UTC

from sqlalchemy.dialects.postgresql import insert as pg_insert


MAX_OTP_ATTEMPTS = 5


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


async def get_valid_otp(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID,
    purpose: OTPPurpose,
):

    result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.user_id == user_id,
            OTPVerification.is_used.is_(False),
            OTPVerification.purpose == purpose,
            OTPVerification.expires_at > datetime.now(UTC),
        )
    )

    return result.scalars().first()


async def record_failed_otp_attempt(
    db: Annotated[AsyncSession, Depends(get_db)],
    otp_row: OTPVerification,
) -> bool:

    otp_row.attempt_count += 1

    invalidated = otp_row.attempt_count >= MAX_OTP_ATTEMPTS

    if invalidated:
        otp_row.is_used = True

    await db.commit()

    return invalidated


async def upsert_otp(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID,
    email: str,
    purpose: OTPPurpose,
    otp_hashed: str,
    expires_at: datetime,
):

    stmt = pg_insert(OTPVerification).values(
        user_id=user_id,
        email=email,
        purpose=purpose,
        otp_hashed=otp_hashed,
        is_used=False,
        attempt_count=0,
        expires_at=expires_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[OTPVerification.user_id, OTPVerification.purpose],
        index_where=text("is_used=false"),
        set_={
            "otp_hashed": stmt.excluded.otp_hashed,
            "email": stmt.excluded.email,
            "expires_at": stmt.excluded.expires_at,
            "attempt_count": 0,
            "created_at": text("now()"),
        },
    )

    return stmt


async def get_user_by_email(
    email: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    return user
