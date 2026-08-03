from fastapi import APIRouter, status, HTTPException, Depends, Request
from typing import Annotated
from src.app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.modules.users.models import User
from sqlalchemy import select, update
from src.app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    CurrentUser,
    create_refresh_token,
    verify_refresh_token,
)
from src.app.modules.users.schemas import (
    UserCreate,
    UserCreateResponse,
    Token,
    RefreshRequest,
    LogoutRequest,
    MessageResponse,
    SendOTPRequest,
    VerifyEmailRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from src.app.core.config import settings

from datetime import datetime, UTC

from src.app.modules.users.models import RefreshToken, OTPPurpose

import uuid

from src.app.modules.users.utils import (
    fetch_refresh_token,
    generate_random_otp,
    get_valid_otp,
    record_failed_otp_attempt,
    upsert_otp,
    get_user_by_email,
)


import secrets


from src.app.modules.users.tasks import (
    send_otp_email_task,
    send_password_reset_email_task,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post(
    "",
    response_model=UserCreateResponse,
)
async def create_user(data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):

    existing_user = await get_user_by_email(data.email, db)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An user with this email already exists",
        )

    new_user = User(
        name=data.name.strip(),
        email=data.email.strip().lower(),
        password_hashed=hash_password(data.password),
    )

    db.add(new_user)

    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post(
    "/token",
    response_model=Token,
)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
):
    result = await db.execute(
        select(User).where(User.email == form_data.username),
    )

    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expire_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    user_ip = request.client.host
    user_agent = request.headers.get("user-agent")

    plain_token, new_token = await create_refresh_token(
        db, user.id, user_ip, user_agent
    )

    await db.commit()

    return Token(
        access_token=access_token,
        refresh_token=f"{new_token.id}.{plain_token}",
        token_type="bearer",
    )


@router.get("/me", response_model=UserCreateResponse)
async def read_current_user(current_user: CurrentUser):
    return current_user


@router.post(
    "/refresh",
    response_model=Token,
)
async def refresh_access_token(
    data: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
):

    rf_token = data.refresh_token

    try:
        token_id, token = rf_token.split(".")
        token_id_uuid = uuid.UUID(token_id)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == token_id_uuid)
    )

    existing_token = result.scalars().first()

    if not existing_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    if not verify_refresh_token(token, existing_token.hashed_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    if existing_token.expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    if existing_token.revoked_at is not None:
        # TODO - log in the logger

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    result = await db.execute(
        select(User).where(User.id == existing_token.user_id),
    )

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either expired or malformed",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expire_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    user_ip = request.client.host
    user_agent = request.headers.get("user-agent")

    plain_token, new_token = await create_refresh_token(
        db, user.id, user_ip, user_agent
    )

    existing_token.revoked_at = datetime.now(UTC)

    await db.commit()
    # await db.refresh(new_token)

    return Token(
        access_token=access_token,
        refresh_token=f"{new_token.id}.{plain_token}",
        token_type="bearer",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_from_current_device(
    data: LogoutRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    try:
        token_id, plain_token = data.refresh_token.split(".")

        token_id_uuid = uuid.UUID(token_id)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either missing or malformed",
        )

    refresh_token_row = await fetch_refresh_token(db, token_id_uuid)

    if (
        refresh_token_row is None
        or refresh_token_row.user_id != current_user.id
        or not verify_refresh_token(plain_token, refresh_token_row.hashed_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The refresh token is either missing or malformed",
        )

    refresh_token_row.revoked_at = datetime.now(UTC)

    await db.commit()


@router.post(
    "/logout/all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout_from_all_devices(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    now = datetime.now(UTC)

    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(
            revoked_at=now,
        )
    )

    await db.execute(stmt)
    await db.commit()


@router.post(
    "/verify-email/send",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="generates a random  digit otp and sends it to the registered email",
)
async def get_verification_email(
    data: SendOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    user = await get_user_by_email(data.email, db)

    if not user or user.is_verified:
        return MessageResponse(
            message="If the email is registered and not verified, an OTP will be sent to the email"
        )

    otp = generate_random_otp(length=6)

    hashed_value = hash_password(otp)

    expires_at = datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes)

    stmt = await upsert_otp(
        db,
        user.id,
        user.email,
        OTPPurpose.EMAIL_VERIFICATION,
        hashed_value,
        expires_at,
    )

    await db.execute(stmt)
    await db.commit()

    send_otp_email_task.delay(
        otp,
        user.email,
    )

    return MessageResponse(
        message="If the email is registered and not verified, an OTP will be sent to the email"
    )


@router.post(
    "/verify-email/confirm",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm email verification OTP",
)
async def confirm_verification_otp(
    data: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_email(data.email, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Please request a new one.",
        )

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already verified.",
        )

    otp_record = await get_valid_otp(db, user.id, OTPPurpose.EMAIL_VERIFICATION)

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP is invalid or has expired. Please request a new one.",
        )

    if not verify_password(data.otp, otp_record.otp_hashed):
        invalidated = await record_failed_otp_attempt(db, otp_record)

        if invalidated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOO many failed attempts,please generate a new otp",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP.",
        )

    otp_record.is_used = True
    user.is_verified = True
    await db.commit()

    return MessageResponse(message="Email verified successfully.")


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset link",
)
async def request_password_reset(
    data: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_email(data.email, db)

    if not user:
        return MessageResponse(
            message="If this email is registered, a password reset link has been sent."
        )

    # await remove_all_valid_otp_for_user(db, user.email, OTPPurpose.PASSWORD_RESET)

    reset_token = secrets.token_urlsafe(32)

    hashed_value = hash_password(reset_token)

    expires_at = datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes)

    stmt = await upsert_otp(
        db,
        user.id,
        user.email,
        OTPPurpose.PASSWORD_RESET,
        hashed_value,
        expires_at,
    )

    await db.execute(stmt)
    await db.commit()

    send_password_reset_email_task.delay(
        to_email=user.email,
        name=user.name,
        reset_token=reset_token,
    )

    return MessageResponse(
        message="If this email is registered, a password reset link has been sent."
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm reset token and set new password",
)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await get_user_by_email(data.email, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Please request a new one.",
        )

    otp_record = await get_valid_otp(db, user.id, OTPPurpose.PASSWORD_RESET)

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Please request a new one.",
        )

    if not verify_password(data.token, otp_record.otp_hashed):
        invalidated = await record_failed_otp_attempt(db, otp_record)

        if invalidated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOO many failed attempts,please generate a new reset link",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset is invalid or has expired. Please request a new one.",
        )

    now = datetime.now(UTC)

    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(
            revoked_at=now,
        )
    )

    await db.execute(stmt)
    otp_record.is_used = True
    user.password_hashed = hash_password(data.new_password)
    await db.commit()

    return MessageResponse(message="Password reset successfully. You can now log in.")
