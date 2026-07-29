import pytest
from httpx2 import ASGITransport, AsyncClient

from src.app.db.database import AsyncSessionLocal, engine
from src.app.main import create_app
from src.app.modules.users.models import RefreshToken, User

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
    from sqlalchemy import delete

    async with AsyncSessionLocal() as session:
        await session.execute(delete(RefreshToken))
        await session.execute(delete(User))
        await session.commit()


async def register_and_login(
    client, email, password="strongpassword123", name="Test User"
):
    """Helper: create a user and log in, returning (access_token, refresh_token)."""
    await client.post(
        "/api/users",
        json={"name": name, "email": email, "password": password},
    )

    response = await client.post(
        "/api/users/token",
        data={"username": email, "password": password},
    )
    data = response.json()
    return data["access_token"], data["refresh_token"]


# ---------------------------------------------------------------------------
# /api/users/logout
# ---------------------------------------------------------------------------


async def test_logout_success(client):
    access_token, refresh_token = await register_and_login(
        client, "logout1@example.com"
    )

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204


async def test_logout_revokes_refresh_token(client):
    access_token, refresh_token = await register_and_login(
        client, "logout2@example.com"
    )

    logout_response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 401


async def test_logout_without_access_token_fails(client):
    _, refresh_token = await register_and_login(client, "logout3@example.com")

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 401


async def test_logout_with_invalid_access_token_fails(client):
    _, refresh_token = await register_and_login(client, "logout4@example.com")

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    assert response.status_code == 401


async def test_logout_with_malformed_refresh_token_fails(client):
    access_token, _ = await register_and_login(client, "logout5@example.com")

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": "not-a-valid-format"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401


async def test_logout_with_nonexistent_refresh_token_id_fails(client):
    import uuid

    access_token, _ = await register_and_login(client, "logout6@example.com")

    fake_token = f"{uuid.uuid4()}.somefakeplaintextsecret"

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": fake_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401


async def test_logout_with_wrong_token_secret_fails(client):
    access_token, refresh_token = await register_and_login(
        client, "logout7@example.com"
    )

    token_id, _plain = refresh_token.split(".")
    tampered_token = f"{token_id}.wrongsecretvalue"

    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": tampered_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401


async def test_logout_with_another_users_refresh_token_fails(client):
    access_token_a, _ = await register_and_login(client, "logout8a@example.com")
    _, refresh_token_b = await register_and_login(client, "logout8b@example.com")

    # User A tries to log out using User B's refresh token
    response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token_b},
        headers={"Authorization": f"Bearer {access_token_a}"},
    )

    assert response.status_code == 401


async def test_logout_does_not_affect_other_sessions(client):
    email = "logout9@example.com"
    password = "strongpassword123"

    await client.post(
        "/api/users",
        json={"name": "Multi Session User", "email": email, "password": password},
    )

    login_1 = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )
    login_2 = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )

    access_token_1 = login_1.json()["access_token"]
    refresh_token_1 = login_1.json()["refresh_token"]
    refresh_token_2 = login_2.json()["refresh_token"]

    logout_response = await client.post(
        "/api/users/logout",
        json={"refresh_token": refresh_token_1},
        headers={"Authorization": f"Bearer {access_token_1}"},
    )
    assert logout_response.status_code == 204

    # The second session's refresh token should still be valid
    refresh_response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": refresh_token_2},
    )
    assert refresh_response.status_code == 200


# ---------------------------------------------------------------------------
# /api/users/logout/all
# ---------------------------------------------------------------------------


async def test_logout_all_success(client):
    access_token, _ = await register_and_login(client, "logoutall1@example.com")

    response = await client.post(
        "/api/users/logout/all",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204


async def test_logout_all_without_access_token_fails(client):
    response = await client.post("/api/users/logout/all")

    assert response.status_code == 401


async def test_logout_all_revokes_every_session(client):
    email = "logoutall2@example.com"
    password = "strongpassword123"

    await client.post(
        "/api/users",
        json={"name": "Multi Session User", "email": email, "password": password},
    )

    login_1 = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )
    login_2 = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )
    login_3 = await client.post(
        "/api/users/token", data={"username": email, "password": password}
    )

    access_token = login_1.json()["access_token"]
    refresh_tokens = [
        login_1.json()["refresh_token"],
        login_2.json()["refresh_token"],
        login_3.json()["refresh_token"],
    ]

    logout_all_response = await client.post(
        "/api/users/logout/all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_all_response.status_code == 204

    for token in refresh_tokens:
        refresh_response = await client.post(
            "/api/users/refresh",
            json={"refresh_token": token},
        )
        assert refresh_response.status_code == 401


async def test_logout_all_does_not_affect_other_users(client):
    access_token_a, _ = await register_and_login(client, "logoutall3a@example.com")
    access_token_b, refresh_token_b = await register_and_login(
        client, "logoutall3b@example.com"
    )

    logout_all_response = await client.post(
        "/api/users/logout/all",
        headers={"Authorization": f"Bearer {access_token_a}"},
    )
    assert logout_all_response.status_code == 204

    # User B's refresh token should still work
    refresh_response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": refresh_token_b},
    )
    assert refresh_response.status_code == 200

    # User B's access token should still work on protected routes too
    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {access_token_b}"},
    )
    assert me_response.status_code == 200


async def test_logout_all_is_idempotent(client):
    access_token, _ = await register_and_login(client, "logoutall4@example.com")

    first_response = await client.post(
        "/api/users/logout/all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert first_response.status_code == 204

    # Calling it again with no active sessions left should still succeed
    second_response = await client.post(
        "/api/users/logout/all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert second_response.status_code == 204
