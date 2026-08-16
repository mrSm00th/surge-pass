from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import get_db
from src.app.modules.organizers.webhook_handlers import (
    apply_account_event,
    apply_product_route_event,
)
from src.app.modules.webhooks.dedup import record_event_if_new
from src.app.modules.webhooks.security import compute_event_hash, verify_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/razorpay", tags=["Webhooks"])

WebhookHandler = Callable[
    [AsyncSession, str, str, dict[str, Any], datetime], Awaitable[None]
]


_EVENT_HANDLERS: dict[str, WebhookHandler] = {
    "account.activated": apply_account_event,
    "account.suspended": apply_account_event,
    "product.route.activated": apply_product_route_event,
    "product.route.under_review": apply_product_route_event,
    "product.route.needs_clarification": apply_product_route_event,
}


@router.post("", status_code=status.HTTP_200_OK)
async def receive_razorpay_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    verify_signature(raw_body, signature)

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Malformed JSON body."
        ) from exc

    event_type = body.get("event", "")
    account_id = body.get("account_id")
    created_at_raw = body.get("created_at")
    event_created_at = (
        datetime.fromtimestamp(created_at_raw, tz=UTC)
        if created_at_raw is not None
        else datetime.now(UTC)
    )

    event_hash = compute_event_hash(raw_body)
    is_new = await record_event_if_new(db, event_hash, event_type, account_id, body)
    if not is_new:
        await db.commit()
        logger.info(
            "Duplicate Razorpay webhook delivery ignored (event=%s).", event_type
        )
        return {"status": "duplicate_ignored"}

    if account_id is None:
        await db.commit()
        logger.error(
            "Webhook '%s' has no top-level account_id - cannot route it to a handler.",
            event_type,
        )
        return {"status": "ignored_no_account_id"}

    handler = _EVENT_HANDLERS.get(event_type)
    if handler is None:
        logger.info("Ignoring unhandled Razorpay webhook event '%s'.", event_type)
    else:
        await handler(db, event_type, account_id, body, event_created_at)

    await db.commit()
    return {"status": "processed"}
