from fastapi.testclient import TestClient
from src.app.main import create_app

client = TestClient(create_app())


def test_health_check():

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
