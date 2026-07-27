from fastapi import APIRouter, status, HTTPException, Depends
from typing import Annotated
from src.app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.modules.users.models import User
from sqlalchemy import select
from src.app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    CurrentUser,
)
from src.app.modules.users.schemas import UserCreate, UserCreateResponse, Token
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from src.app.core.config import settings

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
            status=status.HTTP_409_CONFLICT,
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

    await db.commit()

    return Token(
        access_token=access_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserCreateResponse)
async def read_current_user(current_user: CurrentUser):
    return current_user
