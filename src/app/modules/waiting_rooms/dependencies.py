import uuid

import jwt
from fastapi import HTTPException, Request

from src.app.core.config import settings


def _decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.access_token_secret_key.get_secret_value(),
            algorithms=[settings.access_token_signing_algorithm],
        )
    except jwt.PyJWTError:
        raise HTTPException(403, "Invalid or expired waiting room access token")


def require_waiting_room_access(event_id: uuid.UUID, request: Request) -> dict:
    token = request.cookies.get("access_token") or request.query_params.get("token")
    if not token:
        raise HTTPException(
            403, "No waiting room access token — you haven't been admitted yet"
        )

    payload = _decode_access_token(token)

    if payload.get("typ") != "waiting_room_access":
        raise HTTPException(403, "Token is not a waiting room access token")

    if payload.get("event_id") != str(event_id):
        raise HTTPException(403, "Token does not match this event")

    return payload
