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
)
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from src.app.core.config import settings

from datetime import datetime, UTC

from src.app.modules.users.models import RefreshToken

import uuid

from src.app.modules.users.utils import fetch_refresh_token


router = APIRouter(prefix="/api/users", tags=["users"])


@router.post(
    "",
    response_model=UserCreateResponse,
)
async def create_user(data: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(select(User).where(User.email == data.email))

    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An user with this email already exists",
        )

    new_user = User(
        name=data.name,
        email=data.email,
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
    # new_token = new_token_dict["new_token_row"]
    # plain_token= new_token_dict["plain_token"]

    await db.commit()
    # await db.refresh(new_token)

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
