import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.db.database import get_db
from src.app.modules.users.models import RefreshToken, User

password_hasher = PasswordHash.recommended()

oauth_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")


def hash_password(plain_password: str) -> str:

    return password_hasher.hash(plain_password)


def verify_password(plain_pass: str, hashed_pass: str) -> bool:

    return password_hasher.verify(plain_pass, hashed_pass)


# access token creation
def create_access_token(
    data: dict,
    expire_delta: timedelta | None = None,
) -> str:

    to_encode = data.copy()

    if expire_delta:
        expires = datetime.now(UTC) + expire_delta

    else:
        expires = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes,
        )

    to_encode.update({"exp": expires})

    encoded_jwt_token = jwt.encode(
        to_encode,
        settings.access_token_secret_key.get_secret_value(),
        settings.access_token_signing_algorithm,
    )

    return encoded_jwt_token


def verify_access_token(token: str) -> str | None:

    try:
        payload = jwt.decode(
            token,
            settings.access_token_secret_key.get_secret_value(),
            algorithms=[settings.access_token_signing_algorithm],
            options={"require": ["exp", "sub"]},
        )

    except jwt.InvalidTokenError:
        return None

    else:
        return payload.get("sub")


async def get_current_user(
    token: Annotated[str, Depends(oauth_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:

    user_id = verify_access_token(token)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uuid_user_id = uuid.UUID(user_id)

    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == uuid_user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def generate_token() -> str:

    return secrets.token_urlsafe(32)


def hash_refresh_token(refresh_token: str) -> str:

    return password_hasher.hash(refresh_token)


def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:

    return password_hasher.verify(plain_token, hashed_token)


async def create_refresh_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: uuid.UUID,
    user_ip: str,
    user_agent: str,
):

    new_plain_token = generate_token()
    hashed_rf_token = hash_refresh_token(new_plain_token)

    new_token = RefreshToken(
        hashed_token=hashed_rf_token,
        user_id=user_id,
        user_ip=user_ip,
        user_agent=user_agent,
        expires_at=datetime.now(UTC) + timedelta(settings.refresh_token_expire_days),
    )

    db.add(new_token)

    return new_plain_token, new_token
