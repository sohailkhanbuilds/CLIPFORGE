import os

# Isolate tests from the production Neon database.
os.environ["DATABASE_URL"] = "sqlite:///./test_clipforge.db"
os.environ["CLIPFORGE_API_KEY"] = "test-api-key"
os.environ["CLIPFORGE_ADMIN_KEY"] = "test-admin-key"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
API_HEADERS = {"X-API-Key": "test-api-key"}
ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def test_health_is_public():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_route_rejects_missing_api_key():
    response = client.get("/api/channels")
    assert response.status_code == 401


def test_api_route_rejects_wrong_api_key():
    response = client.get("/api/channels", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_api_route_accepts_valid_api_key():
    response = client.get("/api/channels", headers=API_HEADERS)
    assert response.status_code == 200


def test_new_channel_is_always_unapproved():
    response = client.post(
        "/api/channels",
        headers=API_HEADERS,
        json={
            "name": "Security Test Creator",
            "platform": "youtube",
            "url": "https://www.youtube.com/@security-test-creator",
            "authorized": True,
            "enabled": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["authorized"] is False
    assert response.json()["enabled"] is False
    return response.json()["id"]


def test_normal_api_key_cannot_authorize_creator():
    channel_id = test_new_channel_is_always_unapproved()
    response = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=API_HEADERS,
    )
    assert response.status_code == 401


def test_admin_can_authorize_and_revoke_creator():
    channel_id = test_new_channel_is_always_unapproved()

    approved = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=ADMIN_HEADERS,
    )
    assert approved.status_code == 200
    assert approved.json()["authorized"] is True

    revoked = client.delete(
        f"/api/channels/{channel_id}/authorization",
        headers=ADMIN_HEADERS,
    )
    assert revoked.status_code == 200
    assert revoked.json()["authorized"] is False
    assert revoked.json()["enabled"] is False


def test_unapproved_creator_cannot_be_enabled():
    channel_id = test_new_channel_is_always_unapproved()
    response = client.patch(
        f"/api/channels/{channel_id}?enabled=true",
        headers=API_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
