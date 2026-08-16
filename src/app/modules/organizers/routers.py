from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import get_db
from src.app.modules.organizers.exceptions import (
    RazorpayIntegrationError,
    RazorpayUpstreamError,
    RazorpayValidationError,
    describe,
)
from src.app.modules.organizers.models import KYCStatus, OrganizerProfile
from src.app.modules.organizers.schemas import (
    OrganizerKYCStatusResponse,
    OrganizerKYCSubmitRequest,
    OrganizerProfileResponse,
)
from src.app.modules.organizers.utils import get_current_organizer, submit_organizer_kyc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizers", tags=["Organizers"])


def _status_message(organizer: OrganizerProfile) -> str:

    if organizer.kyc_status == KYCStatus.PENDING:
        return "KYC has not been submitted yet."
    if organizer.kyc_status == KYCStatus.IN_REVIEW:
        return "KYC submitted. Razorpay is reviewing your details."
    if organizer.kyc_status == KYCStatus.ACTION_REQUIRED:
        return "Razorpay needs more information before it can verify this account."
    if organizer.kyc_status == KYCStatus.VERIFIED:
        return "KYC verified."
    if organizer.kyc_status == KYCStatus.REJECTED:
        return "This organizer's KYC was rejected. Contact support to proceed."

    logger.warning(
        "Unhandled KYCStatus '%s' in _status_message for organizer %s.",
        organizer.kyc_status,
        organizer.id,
    )
    return "KYC status is currently being processed."


def _build_kyc_status_response(
    organizer: OrganizerProfile,
) -> OrganizerKYCStatusResponse:
    return OrganizerKYCStatusResponse(
        kyc_status=organizer.kyc_status.value,
        kyc_provider_status=organizer.kyc_provider_status.value
        if organizer.kyc_provider_status
        else None,
        kyc_requirements=organizer.kyc_requirements,
        message=_status_message(organizer),
    )


@router.get("/me", response_model=OrganizerProfileResponse)
async def get_my_organizer_profile(
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
):
    return organizer


@router.get("/kyc/status", response_model=OrganizerKYCStatusResponse)
async def get_kyc_status(
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
):
    return _build_kyc_status_response(organizer)


@router.post("/kyc", response_model=OrganizerKYCStatusResponse)
async def submit_kyc(
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: OrganizerKYCSubmitRequest,
):
    organizer_id = organizer.id

    try:
        organizer = await submit_organizer_kyc(db, organizer, data)
    except RazorpayValidationError as exc:
        await db.commit()
        logger.warning(
            "Razorpay rejected KYC submission for organizer %s: %s",
            organizer_id,
            describe(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Razorpay rejected the submitted details: "
                f"{exc.razorpay_description or 'please check the submitted information and try again.'}"
            ),
        ) from exc
    except RazorpayUpstreamError as exc:
        await db.commit()
        logger.error(
            "Razorpay upstream failure for organizer %s: %s",
            organizer_id,
            describe(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay is temporarily unavailable. Please try submitting again shortly.",
        ) from exc
    except RazorpayIntegrationError as exc:
        await db.commit()
        logger.error(
            "Unclassified Razorpay failure for organizer %s: %s",
            organizer_id,
            describe(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Razorpay to process this KYC submission. Please try again shortly.",
        ) from exc
    else:
        await db.commit()
        await db.refresh(organizer)

    return _build_kyc_status_response(organizer)
