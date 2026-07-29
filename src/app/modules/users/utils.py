from fastapi import Depends
from typing import Annotated
from src.app.db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.app.modules.users.models import RefreshToken

import uuid


async def fetch_refresh_token(
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token_id: uuid.UUID,
):

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == refresh_token_id)
    )

    # handling the case where token is null in the caller func

    return result.scalars().first()


# async def fetch_all_tokens_for_a_user(
#         user_id: uuid.UUID,
#         db: Annotated[AsyncSession,Depends(get_db)],

# ):
#     now = datetime.now(UTC)

#     result = await db.execute(
#         select(RefreshToken)
#         .where(
#             RefreshToken.user_id == user_id,
#             RefreshToken.revoked_at == None,
#             RefreshToken.expires_at>now,
#             )
#     )

#     refresh_tokens = result.scalars().all()

#     return refresh_tokens
