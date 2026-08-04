import pytest
from unittest.mock import patch
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.app.db.database import AsyncSessionLocal, engine
from src.app.main import create_app
from src.app.modules.users.models import RefreshToken, User, OTPVerification

pytestmark = pytest.mark.anyio


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
async def cleanup_users(client):
    yield
    async with AsyncSessionLocal() as session:
        # OTPVerification and RefreshToken both FK to User, so they must
        # be cleared before User is deleted.
        await session.execute(delete(OTPVerification))
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


@pytest.fixture(autouse=True)
def mock_otp_email_task():
    with patch("src.app.modules.users.routers.send_otp_email_task") as mock_task:
        yield mock_task


@pytest.fixture(autouse=True)
def mock_password_reset_email_task():
    with patch(
        "src.app.modules.users.routers.send_password_reset_email_task"
    ) as mock_task:
        yield mock_task


async def register_user(
    client,
    email="otptestuser@example.com",
    password="somepassword123",
    name="OTP Test User",
):
    return await client.post(
        "/api/users",
        json={"name": name, "email": email, "password": password},
    )


async def login(client, email, password):
    response = await client.post(
        "/api/users/token",
        data={"username": email, "password": password},
    )
    return response.json()


def get_sent_otp(mock_task):
    # send_otp_email_task.delay(otp, user.email) -> otp is the first positional arg
    args, _ = mock_task.delay.call_args
    return args[0]


def get_sent_reset_token(mock_task):
    # send_password_reset_email_task.delay(to_email=..., name=..., reset_token=...)
    _, kwargs = mock_task.delay.call_args
    return kwargs["reset_token"]


async def test_send_verification_otp_triggers_email_task(client, mock_otp_email_task):
    email = "verify1@example.com"
    await register_user(client, email=email)

    response = await client.post("/api/users/verify-email/send", json={"email": email})

    assert response.status_code == 200
    mock_otp_email_task.delay.assert_called_once()
    assert get_sent_otp(mock_otp_email_task).isdigit()


async def test_send_verification_otp_nonexistent_email_no_task_triggered(
    client, mock_otp_email_task
):
    response = await client.post(
        "/api/users/verify-email/send", json={"email": "doesnotexist@example.com"}
    )

    # Same generic message either way, to avoid leaking whether the email exists
    assert response.status_code == 200
    mock_otp_email_task.delay.assert_not_called()


async def test_send_verification_otp_already_verified_user_no_task_triggered(
    client, mock_otp_email_task
):
    email = "alreadyverified@example.com"
    password = "somepassword123"
    await register_user(client, email=email, password=password)

    await client.post("/api/users/verify-email/send", json={"email": email})
    otp = get_sent_otp(mock_otp_email_task)
    await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": otp}
    )
    mock_otp_email_task.reset_mock()

    response = await client.post("/api/users/verify-email/send", json={"email": email})

    assert response.status_code == 200
    mock_otp_email_task.delay.assert_not_called()


async def test_confirm_verification_correct_otp_marks_user_verified(
    client, mock_otp_email_task
):
    email = "confirmcorrect@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/verify-email/send", json={"email": email})
    otp = get_sent_otp(mock_otp_email_task)

    response = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": otp}
    )

    assert response.status_code == 200


async def test_confirm_verification_wrong_otp_fails(client, mock_otp_email_task):
    email = "confirmwrong@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/verify-email/send", json={"email": email})

    response = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": "000000"}
    )

    assert response.status_code == 400


async def test_confirm_verification_without_requesting_otp_fails(client):
    email = "neversentotp@example.com"
    await register_user(client, email=email)

    response = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": "123456"}
    )

    assert response.status_code == 400


async def test_confirm_verification_already_verified_conflict(
    client, mock_otp_email_task
):
    email = "doubleconfirm@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/verify-email/send", json={"email": email})
    otp = get_sent_otp(mock_otp_email_task)
    await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": otp}
    )

    response = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": otp}
    )

    assert response.status_code == 409


async def test_confirm_verification_locks_out_after_max_attempts(
    client, mock_otp_email_task
):
    email = "lockout@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/verify-email/send", json={"email": email})

    for _ in range(4):
        response = await client.post(
            "/api/users/verify-email/confirm",
            json={"email": email, "otp": "000000"},
        )
        assert response.status_code == 400
        assert "TOO many" not in response.json()["detail"]

    # 5th failed attempt hits MAX_OTP_ATTEMPTS and invalidates the OTP row
    response = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": "000000"}
    )
    assert response.status_code == 400
    assert "TOO many" in response.json()["detail"]


async def test_requesting_new_otp_invalidates_previous_otp(client, mock_otp_email_task):
    email = "reissue@example.com"
    await register_user(client, email=email)

    await client.post("/api/users/verify-email/send", json={"email": email})
    first_otp = get_sent_otp(mock_otp_email_task)

    await client.post("/api/users/verify-email/send", json={"email": email})
    second_otp = get_sent_otp(mock_otp_email_task)

    stale_attempt = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": first_otp}
    )
    assert stale_attempt.status_code == 400

    fresh_attempt = await client.post(
        "/api/users/verify-email/confirm", json={"email": email, "otp": second_otp}
    )
    assert fresh_attempt.status_code == 200


async def test_password_reset_request_triggers_email_task(
    client, mock_password_reset_email_task
):
    email = "resetrequest@example.com"
    await register_user(client, email=email)

    response = await client.post(
        "/api/users/password-reset/request", json={"email": email}
    )

    assert response.status_code == 200
    mock_password_reset_email_task.delay.assert_called_once()
    assert get_sent_reset_token(mock_password_reset_email_task)


async def test_password_reset_request_nonexistent_email_no_task_triggered(
    client, mock_password_reset_email_task
):
    response = await client.post(
        "/api/users/password-reset/request",
        json={"email": "doesnotexist@example.com"},
    )

    assert response.status_code == 200
    mock_password_reset_email_task.delay.assert_not_called()


async def test_password_reset_confirm_correct_token_changes_password(
    client, mock_password_reset_email_task
):
    email = "resetconfirm@example.com"
    old_password = "oldpassword123"
    new_password = "newpassword456"
    await register_user(client, email=email, password=old_password)

    await client.post("/api/users/password-reset/request", json={"email": email})
    token = get_sent_reset_token(mock_password_reset_email_task)

    response = await client.post(
        "/api/users/password-reset/confirm",
        json={"email": email, "token": token, "new_password": new_password},
    )
    assert response.status_code == 200

    old_login = await login(client, email, old_password)
    assert "access_token" not in old_login

    new_login = await login(client, email, new_password)
    assert "access_token" in new_login


async def test_password_reset_confirm_wrong_token_fails(
    client, mock_password_reset_email_task
):
    email = "resetwrongtoken@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/password-reset/request", json={"email": email})

    response = await client.post(
        "/api/users/password-reset/confirm",
        json={
            "email": email,
            "token": "not-the-real-token",
            "new_password": "somenewpassword",
        },
    )

    assert response.status_code == 400


async def test_password_reset_confirm_locks_out_after_max_attempts(
    client, mock_password_reset_email_task
):
    email = "resetlockout@example.com"
    await register_user(client, email=email)
    await client.post("/api/users/password-reset/request", json={"email": email})

    for _ in range(4):
        response = await client.post(
            "/api/users/password-reset/confirm",
            json={
                "email": email,
                "token": "wrong-token",
                "new_password": "somenewpassword",
            },
        )
        assert response.status_code == 400
        assert "TOO many" not in response.json()["detail"]

    response = await client.post(
        "/api/users/password-reset/confirm",
        json={
            "email": email,
            "token": "wrong-token",
            "new_password": "somenewpassword",
        },
    )
    assert response.status_code == 400
    assert "TOO many" in response.json()["detail"]


async def test_password_reset_confirm_revokes_existing_refresh_tokens(
    client, mock_password_reset_email_task
):
    email = "resetrevokes@example.com"
    password = "oldpassword123"
    await register_user(client, email=email, password=password)
    tokens = await login(client, email, password)
    old_refresh_token = tokens["refresh_token"]

    await client.post("/api/users/password-reset/request", json={"email": email})
    reset_token = get_sent_reset_token(mock_password_reset_email_task)
    await client.post(
        "/api/users/password-reset/confirm",
        json={
            "email": email,
            "token": reset_token,
            "new_password": "newpassword456",
        },
    )

    response = await client.post(
        "/api/users/refresh", json={"refresh_token": old_refresh_token}
    )
    assert response.status_code == 401
