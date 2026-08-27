import uuid

import jwt
from fastapi import HTTPException, Request, status

from src.app.core.config import settings


def _decode_access_token(token: str) -> dict:

    try:
        decoded_data = jwt.decode(
            token,
            settings.access_token_secret_key.get_secret_value(),
            algorithms=[settings.access_token_signing_algorithm],
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired waiting room access token",
        )

    return decoded_data


def require_waiting_room_access(event_id: uuid.UUID, request: Request) -> dict:

    token = request.cookies.get("access_token")
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No waiting room access token — you haven't been admitted yet",
        )

    token_data = _decode_access_token(token)

    if token_data.get("typ") != "waiting_room_access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not a waiting room access token",
        )

    if token_data.get("event_id") != str(event_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not match this event",
        )

    return token_data
