from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.modules.organizers.models import (
    KYCProviderStatus,
    OrganizerProfile,
    RazorpayAccountStatus,
)
from src.app.modules.organizers.utils import map_provider_status_to_kyc_status

logger = logging.getLogger(__name__)


async def _load_organizer_by_account_id(
    db: AsyncSession, account_id: str
) -> OrganizerProfile | None:

    result = await db.execute(
        select(OrganizerProfile)
        .where(OrganizerProfile.razorpay_account_id == account_id)
        .with_for_update()
    )
    return result.scalars().first()


def _extract_requirements(merchant_product_data: Any) -> dict | None:

    if isinstance(merchant_product_data, dict):
        return merchant_product_data.get("requirements")
    return None


async def apply_product_route_event(
    db: AsyncSession,
    event: str,
    account_id: str,
    body: dict[str, Any],
    event_created_at: datetime,
) -> None:

    organizer = await _load_organizer_by_account_id(db, account_id)
    if organizer is None:
        logger.warning(
            "Webhook '%s' for unrecognized Razorpay account_id=%s - no matching organizer.",
            event,
            account_id,
        )
        return

    if (
        organizer.kyc_provider_status_synced_at is not None
        and event_created_at < organizer.kyc_provider_status_synced_at
    ):
        logger.info(
            "Ignoring out-of-order webhook '%s' for organizer %s (event=%s, already synced=%s).",
            event,
            organizer.id,
            event_created_at,
            organizer.kyc_provider_status_synced_at,
        )
        return

    merchant_product = body.get("payload", {}).get("merchant_product", {})
    entity = merchant_product.get("entity", {})
    activation_status_raw = entity.get("activation_status")

    if activation_status_raw is None:
        logger.error(
            "Webhook '%s' missing payload.merchant_product.entity.activation_status.",
            event,
        )
        return

    try:
        provider_status = KYCProviderStatus(activation_status_raw)
    except ValueError:
        logger.error(
            "Unrecognized Razorpay activation_status '%s' in webhook '%s' for organizer %s.",
            activation_status_raw,
            event,
            organizer.id,
        )
        return

    organizer.kyc_provider_status = provider_status
    organizer.kyc_status = map_provider_status_to_kyc_status(provider_status)

    organizer.kyc_requirements = _extract_requirements(merchant_product.get("data"))
    organizer.kyc_provider_status_synced_at = event_created_at

    if (
        provider_status == KYCProviderStatus.ACTIVATED
        and organizer.kyc_activated_at is None
    ):
        organizer.kyc_activated_at = datetime.now(UTC)

    await db.flush()
    logger.info(
        "Organizer %s kyc_provider_status -> %s via webhook '%s'.",
        organizer.id,
        provider_status.value,
        event,
    )


async def apply_account_event(
    db: AsyncSession,
    event: str,
    account_id: str,
    body: dict[str, Any],
    event_created_at: datetime,
) -> None:

    organizer = await _load_organizer_by_account_id(db, account_id)
    if organizer is None:
        logger.warning(
            "Webhook '%s' for unrecognized Razorpay account_id=%s - no matching organizer.",
            event,
            account_id,
        )
        return

    if (
        organizer.razorpay_account_status_synced_at is not None
        and event_created_at < organizer.razorpay_account_status_synced_at
    ):
        logger.info(
            "Ignoring out-of-order webhook '%s' for organizer %s.", event, organizer.id
        )
        return

    new_status = (
        RazorpayAccountStatus.SUSPENDED
        if event == "account.suspended"
        else RazorpayAccountStatus.CREATED
    )
    organizer.razorpay_account_status = new_status
    organizer.razorpay_account_status_synced_at = event_created_at

    await db.flush()
    logger.info(
        "Organizer %s razorpay_account_status -> %s via webhook '%s'.",
        organizer.id,
        new_status.value,
        event,
    )
