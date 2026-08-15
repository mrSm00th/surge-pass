from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.modules.webhooks.models import RazorpayWebhookEvent


async def record_event_if_new(
    db: AsyncSession,
    event_hash: str,
    event_type: str,
    account_id: str | None,
    payload: dict[str, Any],
) -> bool:

    db.add(
        RazorpayWebhookEvent(
            event_hash=event_hash,
            event_type=event_type,
            razorpay_account_id=account_id,
            payload=payload,
        )
    )
    try:
        await db.flush()
        return True

    except IntegrityError:
        await db.rollback()
        return False
