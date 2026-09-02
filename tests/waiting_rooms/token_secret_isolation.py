import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from src.app.core.config import settings
from src.app.modules.waiting_rooms.dependencies import require_waiting_room_access
from src.app.modules.waiting_rooms.services import _issue_access_token


class FakeRequest:
    def __init__(self, cookies: dict | None = None, query_params: dict | None = None):
        self.cookies = cookies or {}
        self.query_params = query_params or {}


def test_a_genuine_waiting_room_token_is_accepted():
    event_id = uuid.uuid4()
    ticket_id = "ticket-abc"

    token = _issue_access_token(event_id, ticket_id)
    request = FakeRequest(cookies={"access_token": token})

    result = require_waiting_room_access(event_id, request)

    assert result["ticket_id"] == ticket_id
    assert result["typ"] == "waiting_room_access"


def test_a_login_token_signed_with_the_login_secret_is_rejected():

    event_id = uuid.uuid4()

    look_alike_payload = {
        "typ": "waiting_room_access",
        "event_id": str(event_id),
        "ticket_id": "ticket-abc",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token_signed_with_login_secret = jwt.encode(
        look_alike_payload,
        settings.access_token_secret_key.get_secret_value(),
        algorithm=settings.access_token_signing_algorithm,
    )

    request = FakeRequest(cookies={"access_token": token_signed_with_login_secret})

    with pytest.raises(HTTPException) as exc_info:
        require_waiting_room_access(event_id, request)

    assert exc_info.value.status_code == 403


def test_a_waiting_room_token_for_a_different_event_is_rejected():
    event_id = uuid.uuid4()
    other_event_id = uuid.uuid4()

    token = _issue_access_token(other_event_id, "ticket-abc")
    request = FakeRequest(cookies={"access_token": token})

    with pytest.raises(HTTPException) as exc_info:
        require_waiting_room_access(event_id, request)

    assert exc_info.value.status_code == 403
    assert "does not match this event" in exc_info.value.detail
