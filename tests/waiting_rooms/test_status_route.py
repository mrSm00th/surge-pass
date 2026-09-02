import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Response

from src.app.modules.waiting_rooms import routers

pytestmark = pytest.mark.anyio


async def test_status_sets_httponly_cookie_and_hides_token_when_admitted():
    event_id = uuid.uuid4()
    current_user = SimpleNamespace(id=uuid.uuid4())
    response = Response()

    with (
        patch.object(
            routers, "_get_published_event", new=AsyncMock(return_value=object())
        ),
        patch.object(
            routers, "get_ticket_id_for_user", new=AsyncMock(return_value="ticket-123")
        ),
        patch.object(
            routers,
            "get_status",
            new=AsyncMock(
                return_value={
                    "admitted": True,
                    "sale_started": True,
                    "access_token": "secret-token-value",
                }
            ),
        ),
    ):
        result = await routers.queue_status(
            event_id, current_user, response, db=None, redis=None
        )

    assert result.admitted is True
    assert not hasattr(result, "access_token")

    set_cookie_header = response.headers.get("set-cookie")
    assert set_cookie_header is not None
    assert "access_token=secret-token-value" in set_cookie_header
    assert "HttpOnly" in set_cookie_header


async def test_status_does_not_set_cookie_when_not_yet_admitted():
    event_id = uuid.uuid4()
    current_user = SimpleNamespace(id=uuid.uuid4())
    response = Response()

    with (
        patch.object(
            routers, "_get_published_event", new=AsyncMock(return_value=object())
        ),
        patch.object(
            routers, "get_ticket_id_for_user", new=AsyncMock(return_value="ticket-456")
        ),
        patch.object(
            routers,
            "get_status",
            new=AsyncMock(
                return_value={
                    "admitted": False,
                    "sale_started": True,
                    "position": 42,
                }
            ),
        ),
    ):
        result = await routers.queue_status(
            event_id, current_user, response, db=None, redis=None
        )

    assert result.admitted is False
    assert result.position == 42
    assert response.headers.get("set-cookie") is None


async def test_status_rejects_when_user_has_no_ticket_for_event():
    event_id = uuid.uuid4()
    current_user = SimpleNamespace(id=uuid.uuid4())
    response = Response()

    with (
        patch.object(
            routers, "_get_published_event", new=AsyncMock(return_value=object())
        ),
        patch.object(
            routers, "get_ticket_id_for_user", new=AsyncMock(return_value=None)
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await routers.queue_status(
                event_id, current_user, response, db=None, redis=None
            )

    assert "join the queue first" in exc_info.value.detail
