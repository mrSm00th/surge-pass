import pytest
from httpx2 import ASGITransport, AsyncClient

from src.app.main import create_app

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


async def test_create_user_success(client):
    response = await client.post(
        "/api/users",
        json={
            "name": "Test User",
            "email": "testuser@example.com",
            "password": "strongpassword123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert "id" in data
    assert "password" not in data
    assert "password_hashed" not in data


async def test_create_user_duplicate_email_fails(client):
    payload = {
        "name": "Dup User",
        "email": "dupuser@example.com",
        "password": "strongpassword123",
    }
    first = await client.post("/api/users", json=payload)
    assert first.status_code == 200

    second = await client.post("/api/users", json=payload)
    assert second.status_code == 409


async def test_login_success_returns_token(client):
    await client.post(
        "/api/users",
        json={
            "name": "Login User",
            "email": "loginuser@example.com",
            "password": "correcthorsebattery",
        },
    )

    response = await client.post(
        "/api/users/token",
        data={
            "username": "loginuser@example.com",
            "password": "correcthorsebattery",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password_fails(client):
    await client.post(
        "/api/users",
        json={
            "name": "Wrong Pass User",
            "email": "wrongpass@example.com",
            "password": "correctpassword",
        },
    )

    response = await client.post(
        "/api/users/token",
        data={
            "username": "wrongpass@example.com",
            "password": "incorrectpassword",
        },
    )
    assert response.status_code == 401


async def test_login_nonexistent_user_fails(client):
    response = await client.post(
        "/api/users/token",
        data={
            "username": "doesnotexist@example.com",
            "password": "whatever",
        },
    )
    assert response.status_code == 401


async def test_access_protected_route_with_valid_token(client):
    await client.post(
        "/api/users",
        json={
            "name": "Protected User",
            "email": "protected@example.com",
            "password": "somepassword123",
        },
    )
    login_response = await client.post(
        "/api/users/token",
        data={
            "username": "protected@example.com",
            "password": "somepassword123",
        },
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def test_access_protected_route_without_token_fails(client):
    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_access_protected_route_with_invalid_token_fails(client):
    response = await client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401
