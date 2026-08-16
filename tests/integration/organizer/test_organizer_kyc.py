import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx2 import ASGITransport, AsyncClient, Response
from razorpay.errors import BadRequestError, ServerError
from sqlalchemy import delete, select, text

from src.app.db.database import AsyncSessionLocal, engine
from src.app.main import create_app
from src.app.modules.organizers.models import (
    KYCProviderStatus,
    KYCStatus,
    OrganizerProfile,
    RazorpayAccountStatus,
)
from src.app.modules.users.models import OTPVerification, RefreshToken, User, UserRole
from src.app.modules.webhooks.models import RazorpayWebhookEvent

pytestmark = pytest.mark.anyio

TEST_WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await engine.dispose()


@pytest.fixture(autouse=True)
async def cleanup(client):
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(RazorpayWebhookEvent))
        await session.execute(delete(OrganizerProfile))
        await session.execute(delete(OTPVerification))
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


# auth and organizer setup helpers
async def register_user(
    client, email, password="somepassword123", name="Organizer Test User"
):
    return await client.post(
        "/api/users", json={"name": name, "email": email, "password": password}
    )


async def login(client, email, password):
    response = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )
    return response.json()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def make_organizer(client, email, password="somepassword123") -> str:

    await register_user(client, email=email, password=password)

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        user.role = UserRole.ORGANIZER
        user.is_verified = True
        session.add(user)
        session.add(OrganizerProfile(user_id=user.id))
        await session.commit()

    tokens = await login(client, email, password)

    return tokens["access_token"]


async def set_organizer_state(email: str, **fields) -> None:

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        organizer = (
            await session.execute(
                select(OrganizerProfile).where(OrganizerProfile.user_id == user.id)
            )
        ).scalar_one()
        for key, value in fields.items():
            setattr(organizer, key, value)
        session.add(organizer)
        await session.commit()


async def get_organizer(email: str) -> OrganizerProfile:
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        return (
            await session.execute(
                select(OrganizerProfile).where(OrganizerProfile.user_id == user.id)
            )
        ).scalar_one()


#  KYC payload builder


def make_kyc_payload(**overrides) -> dict:
    payload = {
        "legal_business_name": "Test Events Pvt Ltd",
        "business_type": "private_limited",
        "pan_number": "ABCDE1234F",
        "gst_number": None,
        "contact_email": "kyc-contact@example.com",
        "contact_phone": "9876543210",
        "bank_account_number": "123456789012",
        "bank_ifsc": "HDFC0000123",
        "bank_beneficiary_name": "Test Events Pvt Ltd",
        "stakeholder": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "9876543211",
            "percentage_ownership": 100,
            "is_director": True,
            "address": {
                "street": "123 Test Street",
                "city": "Mumbai",
                "state": "Maharashtra",
                "postal_code": "400001",
                "country": "IN",
            },
        },
        "tnc_accepted": True,
    }
    payload.update(overrides)
    return payload


#  Razorpay SDK mocking


@pytest.fixture
def mock_razorpay():
    with (
        patch(
            "src.app.modules.organizers.utils.razorpay_client.account.create"
        ) as account_create,
        patch(
            "src.app.modules.organizers.utils.razorpay_client.stakeholder.create"
        ) as stakeholder_create,
        patch(
            "src.app.modules.organizers.utils.razorpay_client.stakeholder.edit"
        ) as stakeholder_edit,
        patch(
            "src.app.modules.organizers.utils.razorpay_client.product.requestProductConfiguration"
        ) as product_request,
        patch(
            "src.app.modules.organizers.utils.razorpay_client.product.edit"
        ) as product_edit,
    ):
        account_create.return_value = {"id": "acc_TestAccount123", "status": "created"}
        stakeholder_create.return_value = {"id": "sth_TestStakeholder123"}
        stakeholder_edit.return_value = {"id": "sth_TestStakeholder123"}
        product_request.return_value = {
            "id": "acc_prd_Test123",
            "activation_status": "under_review",
        }
        product_edit.return_value = {
            "id": "acc_prd_Test123",
            "activation_status": "under_review",
        }

        yield {
            "account_create": account_create,
            "stakeholder_create": stakeholder_create,
            "stakeholder_edit": stakeholder_edit,
            "product_request": product_request,
            "product_edit": product_edit,
        }


# KYC submission


async def test_submit_kyc_requires_organizer_role(client):
    await register_user(client, email="notanorganizer@example.com")
    tokens = await login(client, "notanorganizer@example.com", "somepassword123")

    response = await client.post(
        "/api/organizers/kyc",
        json=make_kyc_payload(),
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 403


async def test_submit_kyc_first_submission_under_review(client, mock_razorpay):
    email = "kyc-first@example.com"
    token = await make_organizer(client, email)

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kyc_status"] == "IN_REVIEW"
    assert body["kyc_provider_status"] == "under_review"

    mock_razorpay["account_create"].assert_called_once()
    mock_razorpay["stakeholder_create"].assert_called_once()
    mock_razorpay["product_request"].assert_called_once()

    organizer = await get_organizer(email)
    assert organizer.razorpay_account_id == "acc_TestAccount123"
    assert organizer.razorpay_stakeholder_id == "sth_TestStakeholder123"
    assert organizer.razorpay_product_id == "acc_prd_Test123"

    sent_reference_id = mock_razorpay["account_create"].call_args[0][0]["reference_id"]
    assert sent_reference_id == organizer.razorpay_reference_code
    assert len(sent_reference_id) <= 20


async def test_submit_kyc_first_submission_activated_immediately(client, mock_razorpay):
    email = "kyc-activated@example.com"
    token = await make_organizer(client, email)
    mock_razorpay["product_request"].return_value = {
        "id": "acc_prd_Test123",
        "activation_status": "activated",
    }

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 200
    assert response.json()["kyc_status"] == "VERIFIED"

    organizer = await get_organizer(email)
    assert organizer.kyc_status == KYCStatus.VERIFIED
    assert organizer.kyc_activated_at is not None


async def test_submit_kyc_already_verified_returns_409(client, mock_razorpay):
    email = "kyc-already-verified@example.com"
    token = await make_organizer(client, email)
    await set_organizer_state(
        email,
        kyc_status=KYCStatus.VERIFIED,
        kyc_provider_status=KYCProviderStatus.ACTIVATED,
        razorpay_account_id="acc_x",
        razorpay_stakeholder_id="sth_x",
        razorpay_product_id="prd_x",
        legal_business_name="Existing Biz",
        bank_account_number="000",
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 409
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_already_in_review_returns_409(client, mock_razorpay):
    email = "kyc-already-in-review@example.com"
    token = await make_organizer(client, email)
    await set_organizer_state(
        email,
        kyc_status=KYCStatus.IN_REVIEW,
        kyc_provider_status=KYCProviderStatus.UNDER_REVIEW,
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 409
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_rejected_returns_409(client, mock_razorpay):
    email = "kyc-rejected@example.com"
    token = await make_organizer(client, email)

    await set_organizer_state(
        email,
        kyc_status=KYCStatus.REJECTED,
        kyc_provider_status=KYCProviderStatus.SUSPENDED,
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 409
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_suspended_payout_account_returns_409(client, mock_razorpay):
    email = "kyc-account-suspended@example.com"
    token = await make_organizer(client, email)
    await set_organizer_state(
        email, razorpay_account_status=RazorpayAccountStatus.SUSPENDED
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 409
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_tnc_not_accepted_rejected_before_razorpay_call(
    client, mock_razorpay
):
    email = "kyc-no-tnc@example.com"
    token = await make_organizer(client, email)

    response = await client.post(
        "/api/organizers/kyc",
        json=make_kyc_payload(tnc_accepted=False),
        headers=auth_headers(token),
    )

    assert response.status_code == 422
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_invalid_pan_format_rejected_before_razorpay_call(
    client, mock_razorpay
):
    email = "kyc-bad-pan@example.com"
    token = await make_organizer(client, email)

    response = await client.post(
        "/api/organizers/kyc",
        json=make_kyc_payload(pan_number="NOTAPAN123"),
        headers=auth_headers(token),
    )

    assert response.status_code == 422
    mock_razorpay["account_create"].assert_not_called()


async def test_submit_kyc_razorpay_bad_request_returns_400(client, mock_razorpay):
    email = "kyc-bad-request@example.com"
    token = await make_organizer(client, email)
    mock_razorpay["account_create"].side_effect = BadRequestError(
        "Invalid business_type for this category"
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 400


async def test_submit_kyc_razorpay_server_error_returns_502(client, mock_razorpay):
    email = "kyc-server-error@example.com"
    token = await make_organizer(client, email)
    mock_razorpay["account_create"].side_effect = ServerError(
        "Razorpay had an internal error"
    )

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 502


async def test_submit_kyc_partial_failure_preserves_completed_steps(
    client, mock_razorpay
):

    email = "kyc-partial-failure@example.com"
    token = await make_organizer(client, email)
    mock_razorpay["stakeholder_create"].side_effect = ServerError("timeout")

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 502

    organizer = await get_organizer(email)

    assert organizer.razorpay_account_id == "acc_TestAccount123"
    assert organizer.razorpay_reference_code is not None

    assert organizer.razorpay_stakeholder_id is None
    assert organizer.razorpay_product_id is None


async def test_submit_kyc_retry_after_partial_failure_does_not_recreate_account(
    client, mock_razorpay
):
    email = "kyc-retry@example.com"
    token = await make_organizer(client, email)
    mock_razorpay["stakeholder_create"].side_effect = ServerError("timeout")

    first = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )
    assert first.status_code == 502

    mock_razorpay["stakeholder_create"].side_effect = None
    mock_razorpay["stakeholder_create"].return_value = {"id": "sth_TestStakeholder123"}

    second = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert second.status_code == 200

    mock_razorpay["account_create"].assert_called_once()

    assert mock_razorpay["stakeholder_create"].call_count == 2


async def test_submit_kyc_resubmission_after_needs_clarification_uses_edit_calls(
    client, mock_razorpay
):
    email = "kyc-resubmit@example.com"
    token = await make_organizer(client, email)
    await set_organizer_state(
        email,
        kyc_status=KYCStatus.ACTION_REQUIRED,
        kyc_provider_status=KYCProviderStatus.NEEDS_CLARIFICATION,
        razorpay_reference_code="existingrefcode1234",
        razorpay_account_id="acc_TestAccount123",
        razorpay_stakeholder_id="sth_TestStakeholder123",
        razorpay_product_id="acc_prd_Test123",
    )
    mock_razorpay["product_edit"].return_value = {
        "id": "acc_prd_Test123",
        "activation_status": "activated",
    }

    response = await client.post(
        "/api/organizers/kyc", json=make_kyc_payload(), headers=auth_headers(token)
    )

    assert response.status_code == 200
    assert response.json()["kyc_status"] == "VERIFIED"

    mock_razorpay["account_create"].assert_not_called()
    mock_razorpay["stakeholder_create"].assert_not_called()
    mock_razorpay["stakeholder_edit"].assert_called_once()
    mock_razorpay["product_edit"].assert_called_once()


async def test_submit_kyc_pan_is_encrypted_at_rest(client, mock_razorpay):
    email = "kyc-encryption@example.com"
    token = await make_organizer(client, email)

    await client.post(
        "/api/organizers/kyc",
        json=make_kyc_payload(pan_number="abcde1234f"),
        headers=auth_headers(token),
    )

    async with AsyncSessionLocal() as session:
        raw = await session.execute(
            text(
                "SELECT op.pan_number FROM organizer_profiles op "
                "JOIN users u ON u.id = op.user_id "
                "WHERE u.email = :email"
            ),
            {"email": email},
        )
        stored_ciphertext = raw.scalar_one()

    assert stored_ciphertext != "ABCDE1234F"
    assert "ABCDE1234F" not in stored_ciphertext

    organizer = await get_organizer(email)
    assert organizer.pan_number == "ABCDE1234F"  # normalized + decrypted on read


# Webhooks


def sign(raw_body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def make_product_route_event(
    account_id: str,
    event: str,
    activation_status: str,
    requirements: list | None = None,
    created_at: int | None = None,
) -> dict:
    return {
        "entity": "event",
        "account_id": account_id,
        "event": event,
        "contains": ["merchant_product"],
        "payload": {
            "merchant_product": {
                "entity": {
                    "id": "acc_prd_Test123",
                    "merchant_id": account_id,
                    "activation_status": activation_status,
                },
                "data": {"requirements": requirements}
                if requirements is not None
                else [],
            }
        },
        "created_at": created_at
        if created_at is not None
        else int(datetime.now(UTC).timestamp()),
    }


def make_account_event(
    account_id: str, event: str, created_at: int | None = None
) -> dict:
    return {
        "entity": "event",
        "account_id": account_id,
        "event": event,
        "contains": ["account"],
        "payload": {
            "account": {
                "entity": {
                    "id": account_id.removeprefix("acc_"),
                    "entity": "merchant",
                    "activated": event == "account.activated",
                }
            }
        },
        "created_at": created_at
        if created_at is not None
        else int(datetime.now(UTC).timestamp()),
    }


@pytest.fixture
def webhook_secret():

    with patch(
        "src.app.modules.webhooks.security.settings.razorpay_webhook_secret",
        TEST_WEBHOOK_SECRET,
    ):
        yield TEST_WEBHOOK_SECRET


async def post_webhook(client, event: dict) -> Response:
    raw_body = json.dumps(event).encode("utf-8")
    return await client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sign(raw_body),
        },
    )


async def test_webhook_missing_signature_header_returns_400(client, webhook_secret):
    event = make_product_route_event("acc_x", "product.route.activated", "activated")
    response = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


async def test_webhook_invalid_signature_returns_400(client, webhook_secret):
    event = make_product_route_event("acc_x", "product.route.activated", "activated")
    response = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(event).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "not-a-real-signature",
        },
    )

    assert response.status_code == 400


async def test_webhook_activated_updates_organizer(
    client, webhook_secret, mock_razorpay
):
    email = "webhook-activated@example.com"
    token = await make_organizer(client, email)  # noqa: F841

    await set_organizer_state(
        email,
        razorpay_account_id="acc_WebhookTest1",
        razorpay_stakeholder_id="sth_WebhookTest1",
        razorpay_product_id="prd_WebhookTest1",
        legal_business_name="Webhook Test Biz",
        bank_account_number="1234567890",
    )

    event = make_product_route_event(
        "acc_WebhookTest1", "product.route.activated", "activated"
    )
    response = await post_webhook(client, event)

    assert response.status_code == 200
    organizer = await get_organizer(email)
    assert organizer.kyc_status == KYCStatus.VERIFIED
    assert organizer.kyc_provider_status == KYCProviderStatus.ACTIVATED
    assert organizer.kyc_activated_at is not None


async def test_webhook_needs_clarification_sets_requirements(client, webhook_secret):
    email = "webhook-clarify@example.com"
    token = await make_organizer(client, email)  # noqa: F841
    await set_organizer_state(email, razorpay_account_id="acc_WebhookTest2")

    requirements = [
        {"field_reference": "settlements.ifsc_code", "reason_code": "invalid_ifsc"}
    ]
    event = make_product_route_event(
        "acc_WebhookTest2",
        "product.route.needs_clarification",
        "needs_clarification",
        requirements=requirements,
    )
    response = await post_webhook(client, event)

    assert response.status_code == 200
    organizer = await get_organizer(email)
    assert organizer.kyc_status == KYCStatus.ACTION_REQUIRED

    assert organizer.kyc_requirements == requirements


async def test_webhook_account_suspended_updates_organizer(client, webhook_secret):
    email = "webhook-suspended@example.com"
    token = await make_organizer(client, email)  # noqa: F841
    await set_organizer_state(email, razorpay_account_id="acc_WebhookTest3")

    event = make_account_event("acc_WebhookTest3", "account.suspended")
    response = await post_webhook(client, event)

    assert response.status_code == 200
    organizer = await get_organizer(email)
    assert organizer.razorpay_account_status == RazorpayAccountStatus.SUSPENDED


async def test_webhook_duplicate_delivery_is_ignored(client, webhook_secret):
    email = "webhook-duplicate@example.com"
    token = await make_organizer(client, email)  # noqa: F841
    await set_organizer_state(
        email,
        razorpay_account_id="acc_WebhookTest4",
        razorpay_stakeholder_id="sth_WebhookTest4",
        razorpay_product_id="prd_WebhookTest4",
        legal_business_name="Webhook Test Biz",
        bank_account_number="1234567890",
    )

    event = make_product_route_event(
        "acc_WebhookTest4", "product.route.activated", "activated"
    )
    raw_body = json.dumps(event).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sign(raw_body),
    }

    first = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)
    second = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)

    assert first.status_code == 200
    assert first.json()["status"] == "processed"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate_ignored"

    async with AsyncSessionLocal() as session:
        count = (await session.execute(select(RazorpayWebhookEvent))).scalars().all()
    assert len(count) == 1


async def test_webhook_out_of_order_delivery_does_not_regress_status(
    client, webhook_secret
):
    email = "webhook-out-of-order@example.com"
    token = await make_organizer(client, email)  # noqa : F841
    await set_organizer_state(
        email,
        razorpay_account_id="acc_WebhookTest5",
        razorpay_stakeholder_id="sth_WebhookTest5",
        razorpay_product_id="prd_WebhookTest5",
        legal_business_name="Webhook Test Biz",
        bank_account_number="1234567890",
    )

    now = int(datetime.now(UTC).timestamp())
    newer = make_product_route_event(
        "acc_WebhookTest5", "product.route.activated", "activated", created_at=now
    )
    older_but_late = make_product_route_event(
        "acc_WebhookTest5",
        "product.route.under_review",
        "under_review",
        created_at=now - 3600,
    )

    await post_webhook(client, newer)
    response = await post_webhook(client, older_but_late)

    assert response.status_code == 200
    organizer = await get_organizer(email)

    assert organizer.kyc_status == KYCStatus.VERIFIED
    assert organizer.kyc_provider_status == KYCProviderStatus.ACTIVATED


async def test_webhook_unknown_account_id_returns_200_and_does_nothing(
    client, webhook_secret
):
    event = make_product_route_event(
        "acc_DoesNotExist", "product.route.activated", "activated"
    )
    response = await post_webhook(client, event)

    assert response.status_code == 200
    assert response.json()["status"] == "processed"


async def test_webhook_unrecognized_event_type_returns_200(client, webhook_secret):
    event = make_product_route_event(
        "acc_x", "product.route.some_future_event", "activated"
    )
    event["event"] = "product.route.some_future_event"
    response = await post_webhook(client, event)

    assert response.status_code == 200
