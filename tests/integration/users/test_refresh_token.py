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
    client, email="refreshtest@example.com", password="somepassword123"
):
    await client.post(
        "/api/users",
        json={"name": "Refresh Test User", "email": email, "password": password},
    )
    login_response = await client.post(
        "/api/users/token",
        data={"username": email, "password": password},
    )
    return login_response.json()


async def test_login_returns_refresh_token(client):
    tokens = await register_and_login(client)
    assert "refresh_token" in tokens
    assert "." in tokens["refresh_token"]


async def test_refresh_with_valid_token_returns_new_tokens(client):
    tokens = await register_and_login(client)

    response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != tokens["refresh_token"]


async def test_refresh_with_malformed_token_fails(client):
    response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": "not-a-valid-format"},
    )
    assert response.status_code == 401


async def test_refresh_with_nonexistent_token_id_fails(client):
    import uuid

    fake_id = uuid.uuid4()
    response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": f"{fake_id}.somefaketoken"},
    )
    assert response.status_code == 401


async def test_refresh_with_wrong_secret_fails(client):
    tokens = await register_and_login(client)
    token_id = tokens["refresh_token"].split(".")[0]

    response = await client.post(
        "/api/users/refresh",
        json={"refresh_token": f"{token_id}.wrongsecretvalue"},
    )
    assert response.status_code == 401


async def test_old_refresh_token_is_revoked_after_use(client):
    tokens = await register_and_login(client)
    old_refresh_token = tokens["refresh_token"]

    first_refresh = await client.post(
        "/api/users/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert first_refresh.status_code == 200

    second_attempt = await client.post(
        "/api/users/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert second_attempt.status_code == 401
