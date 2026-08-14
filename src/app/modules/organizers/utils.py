import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Callable

import requests
from fastapi import Depends, HTTPException, status
from razorpay.errors import BadRequestError, GatewayError, ServerError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.dependencies import require_roles
from src.app.core.razorpay_client import razorpay_client
from src.app.db.database import get_db
from src.app.modules.organizers.exceptions import (
    RazorpayIntegrationError,
    RazorpayUpstreamError,
    RazorpayValidationError,
)
from src.app.modules.organizers.models import (
    KYCProviderStatus,
    KYCStatus,
    OrganizerProfile,
    RazorpayAccountStatus,
)
from src.app.modules.organizers.schemas import OrganizerKYCSubmitRequest
from src.app.modules.users.models import User, UserRole

logger = logging.getLogger(__name__)


REFERENCE_CODE_LENGTH = 20


# a mapping of KYCProviderStatus to the in app KYCStatus
_PROVIDER_TO_BUSINESS_STATUS: dict[KYCProviderStatus, KYCStatus] = {
    KYCProviderStatus.REQUESTED: KYCStatus.IN_REVIEW,
    KYCProviderStatus.UNDER_REVIEW: KYCStatus.IN_REVIEW,
    KYCProviderStatus.NEEDS_CLARIFICATION: KYCStatus.ACTION_REQUIRED,
    KYCProviderStatus.ACTIVATED: KYCStatus.VERIFIED,
    KYCProviderStatus.SUSPENDED: KYCStatus.REJECTED,
}


def map_provider_status_to_kyc_status(provider_status: KYCProviderStatus) -> KYCStatus:
    return _PROVIDER_TO_BUSINESS_STATUS[provider_status]


# wrapper function to wrap every rz pay call and act as a centralized exception translator
async def _call_razorpay(
    step: str,
    fn: Callable[..., dict[str, Any]],
    *args: Any,
) -> dict[str, Any]:

    try:
        return await asyncio.to_thread(fn, *args)

    except BadRequestError as exc:
        raise RazorpayValidationError(step, exc) from exc

    except (GatewayError, ServerError) as exc:
        raise RazorpayUpstreamError(step, exc) from exc

    # catching timeout, DNS or connection reset errors
    except requests.exceptions.RequestException as exc:
        raise RazorpayUpstreamError(step, exc) from exc

    except Exception as exc:
        logger.exception("Unclassified error calling Razorpay during '%s'", step)
        raise RazorpayIntegrationError(step, exc) from exc


async def get_or_create_organizer_profile(
    db: AsyncSession,
    user: User,
) -> OrganizerProfile:

    if user.role == UserRole.ORGANIZER:
        result = await db.execute(
            select(OrganizerProfile).where(OrganizerProfile.user_id == user.id)
        )

        organizer_profile = result.scalars().first()

        if not organizer_profile:
            raise ValueError(
                f"Organizer profile not found for user {user.id} with role ORGANIZER"
            )

        return organizer_profile

    user.role = UserRole.ORGANIZER
    db.add(user)

    organizer = OrganizerProfile(user_id=user.id)
    db.add(organizer)

    await db.flush()
    return organizer


async def get_organizer_profile_by_user_id(
    db: AsyncSession,
    user_id: str,
) -> OrganizerProfile:

    result = await db.execute(
        select(OrganizerProfile).where(OrganizerProfile.user_id == user_id)
    )

    organizer_profile = result.scalars().first()

    if not organizer_profile:
        raise ValueError(
            f"Organizer profile not found for user {user_id} with role ORGANIZER"
        )

    return organizer_profile


async def get_current_organizer(
    current_user: Annotated[User, Depends(require_roles(UserRole.ORGANIZER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizerProfile:
    result = await db.execute(
        select(OrganizerProfile).where(OrganizerProfile.user_id == current_user.id)
    )
    organizer = result.scalars().first()

    if not organizer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organizer profile not found for user with ORGANIZER role.",
        )
    return organizer


async def get_verified_organizer(
    organizer: Annotated[OrganizerProfile, Depends(get_current_organizer)],
) -> OrganizerProfile:
    if organizer.kyc_status != KYCStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete KYC verification before performing this action.",
        )
    return organizer


async def _create_razorpay_account(
    organizer: OrganizerProfile,
    payload: OrganizerKYCSubmitRequest,
):

    try:
        new_razorpay_account = await _call_razorpay(
            "account.create",
            {
                "email": payload.contact_email,
                "phone": payload.contact_phone,
                "type": "route",
                "reference_id": str(organizer.id),
                "legal_business_name": payload.legal_business_name,
                "business_type": str,
                "contact_name": payload.stakeholder.name,
                "profile": {
                    "category": "event_management",
                    "subcategory": "event_management_services",
                    "addresses": {
                        "registered": {
                            "street1": payload.stakeholder.address.street,
                            "city": payload.stakeholder.address.city,
                            "state": payload.stakeholder.address.state,
                            "postal_code": payload.stakeholder.address.postal_code,
                            "country": payload.stakeholder.address.country,
                        }
                    },
                },
            },
        )

    except Exception:
        raise ValueError("something went wrong, check your request and try again")

    return new_razorpay_account


# creating stakeholder for the linked account


async def _create_razorpay_stakeholder(
    organizer: OrganizerProfile,
    payload: OrganizerKYCSubmitRequest,
) -> dict[str, Any]:

    if organizer.razorpay_account_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay account ID"),
        )

    try:
        new_stakeholder = await _call_razorpay(
            "stakeholder.create",
            organizer.razorpay_account_id,
            {
                "name": payload.stakeholder.name,
                "email": payload.stakeholder.email,
                "percentage_ownership": payload.stakeholder.percentage_ownership,
                "relationship": {"director": payload.stakeholder.is_director},
                "phone": {"primary": payload.stakeholder.phone},
                "addresses": {
                    "residential": {
                        "street": payload.stakeholder.address.street,
                        "city": payload.stakeholder.address.city,
                        "state": payload.stakeholder.address.state,
                        "postal_code": payload.stakeholder.address.postal_code,
                        "country": payload.stakeholder.address.country,
                    }
                },
                "kyc": {"pan": payload.pan_number},
            },
        )
    except Exception as exc:
        raise RazorpayIntegrationError("stakeholder.create", exc) from exc

    return new_stakeholder


async def _edit_razorpay_stakeholder(
    organizer: OrganizerProfile,
    payload: OrganizerKYCSubmitRequest,
) -> dict[str, Any]:

    if organizer.razorpay_account_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay account ID"),
        )

    if organizer.razorpay_stakeholder_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay stakeholder ID"),
        )

    try:
        return await _call_razorpay(
            "stakeholder.edit",
            razorpay_client.stakeholder.edit,
            organizer.razorpay_account_id,
            organizer.razorpay_stakeholder_id,
            {
                "name": payload.stakeholder.name,
                "percentage_ownership": payload.stakeholder.percentage_ownership,
                "relationship": {"director": payload.stakeholder.is_director},
                "phone": {"primary": payload.stakeholder.phone},
                "addresses": {
                    "residential": {
                        "street": payload.stakeholder.address.street,
                        "city": payload.stakeholder.address.city,
                        "state": payload.stakeholder.address.state,
                        "postal_code": payload.stakeholder.address.postal_code,
                        "country": payload.stakeholder.address.country,
                    }
                },
                "kyc": {"pan": payload.pan_number},
            },
        )
    except Exception as exc:
        raise RazorpayIntegrationError("stakeholder.edit", exc) from exc


async def _request_razorpay_product_config(
    organizer: OrganizerProfile, payload: OrganizerKYCSubmitRequest
) -> dict[str, Any]:

    if organizer.razorpay_account_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay account ID"),
        )

    try:
        return await _call_razorpay(
            "product.requestProductConfiguration",
            razorpay_client.product.requestProductConfiguration,
            organizer.razorpay_account_id,
            {
                "product_name": "route",
                "tnc_accepted": payload.tnc_accepted,
                "data": {
                    "settlements": {
                        "account_number": payload.bank_account_number,
                        "ifsc_code": payload.bank_ifsc,
                        "beneficiary_name": payload.bank_beneficiary_name,
                    }
                },
            },
        )
    except Exception as exc:
        raise RazorpayIntegrationError(
            "product.requestProductConfiguration", exc
        ) from exc


async def _edit_razorpay_product_config(
    organizer: OrganizerProfile, payload: OrganizerKYCSubmitRequest
) -> dict[str, Any]:

    if organizer.razorpay_account_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay account ID"),
        )

    if organizer.razorpay_stakeholder_id is None:
        raise RazorpayIntegrationError(
            "stakeholder.edit",
            ValueError("Organizer has no Razorpay stakeholder ID"),
        )

    try:
        return await _call_razorpay(
            "product.edit",
            razorpay_client.product.edit,
            organizer.razorpay_account_id,
            organizer.razorpay_product_id,
            {
                "settlements": {
                    "account_number": payload.bank_account_number,
                    "ifsc_code": payload.bank_ifsc,
                    "beneficiary_name": payload.bank_beneficiary_name,
                }
            },
        )
    except Exception as exc:
        raise RazorpayIntegrationError("product.edit", exc) from exc


def _guard_kyc_submittable_state(organizer: OrganizerProfile) -> None:

    if organizer.kyc_status == KYCStatus.VERIFIED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "KYC is already verified for this organizer."
        )

    if organizer.kyc_status == KYCStatus.REJECTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Your organizer's KYC was rejected. Contact support to proceed.",
        )

    if organizer.razorpay_account_status == RazorpayAccountStatus.SUSPENDED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Your organizer's payout account is suspended. Contact support.",
        )

    if organizer.kyc_status == KYCStatus.IN_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "KYC has already been submitted and is under review with Razorpay.",
        )


def _apply_kyc_input_to_profile(
    organizer: OrganizerProfile, payload: OrganizerKYCSubmitRequest
) -> None:

    organizer.legal_business_name = payload.legal_business_name
    organizer.business_type = payload.business_type
    organizer.pan_number = payload.pan_number
    organizer.gst_number = payload.gst_number
    organizer.contact_email = payload.contact_email
    organizer.contact_phone = payload.contact_phone
    organizer.bank_account_number = payload.bank_account_number
    organizer.bank_ifsc = payload.bank_ifsc
    organizer.bank_beneficiary_name = payload.bank_beneficiary_name


async def _allocate_reference_code(db: AsyncSession) -> str:

    for _ in range(5):
        code = uuid.uuid4().hex[:REFERENCE_CODE_LENGTH]
        existing = await db.execute(
            select(OrganizerProfile.id).where(
                OrganizerProfile.razorpay_reference_code == code
            )
        )
        if existing.scalar_one_or_none() is None:
            return code
    raise RuntimeError(
        "Could not allocate a unique Razorpay reference code after 5 attempts."
    )


async def submit_organizer_kyc(
    db: AsyncSession,
    organizer: OrganizerProfile,
    payload: OrganizerKYCSubmitRequest,
) -> OrganizerProfile:

    _guard_kyc_submittable_state(organizer)
    is_resubmission = organizer.kyc_status == KYCStatus.ACTION_REQUIRED

    _apply_kyc_input_to_profile(organizer, payload)
    await db.flush()

    if organizer.razorpay_reference_code is None:
        organizer.razorpay_reference_code = await _allocate_reference_code(db)
        await db.flush()

    if organizer.razorpay_account_id is None:
        account = await _create_razorpay_account(organizer, payload)
        organizer.razorpay_account_id = account["id"]
        organizer.razorpay_account_status = RazorpayAccountStatus(account["status"])
        await db.flush()

    if organizer.razorpay_stakeholder_id is None:
        stakeholder = await _create_razorpay_stakeholder(organizer, payload)
        organizer.razorpay_stakeholder_id = stakeholder["id"]
        await db.flush()
    elif is_resubmission:
        await _edit_razorpay_stakeholder(organizer, payload)

    if organizer.razorpay_product_id is None:
        product = await _request_razorpay_product_config(organizer, payload)
        organizer.razorpay_product_id = product["id"]
    else:
        product = await _edit_razorpay_product_config(organizer, payload)

    organizer.kyc_provider_status = KYCProviderStatus(product["activation_status"])
    organizer.kyc_status = map_provider_status_to_kyc_status(
        organizer.kyc_provider_status
    )
    organizer.kyc_requirements = product.get("requirements")

    if organizer.kyc_submitted_at is None:
        organizer.kyc_submitted_at = datetime.now(UTC)
    if organizer.kyc_provider_status == KYCProviderStatus.ACTIVATED:
        organizer.kyc_activated_at = datetime.now(UTC)

    await db.flush()

    return organizer
