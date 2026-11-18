import os
from uuid import uuid4

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


def create_unapproved_channel():
    handle = uuid4().hex
    response = client.post(
        "/api/channels",
        headers=API_HEADERS,
        json={
            "name": "Security Test Creator",
            "platform": "youtube",
            "url": f"https://www.youtube.com/@security-test-{handle}",
            "authorized": True,
            "enabled": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["authorized"] is False
    assert response.json()["enabled"] is False
    return response.json()["id"]


def test_normal_api_key_cannot_authorize_creator():
    channel_id = create_unapproved_channel()
    response = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=API_HEADERS,
    )
    assert response.status_code == 401


def test_admin_can_authorize_and_revoke_creator():
    channel_id = create_unapproved_channel()

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
    channel_id = create_unapproved_channel()
    response = client.patch(
        f"/api/channels/{channel_id}?enabled=true",
        headers=API_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_task_routes_reject_missing_api_key():
    response = client.get("/api/tasks")
    assert response.status_code == 401


def test_task_creation_rejects_missing_api_key():
    response = client.post(
        "/api/tasks",
        json={
            "video_url": "https://www.youtube.com/watch?v=securitytest",
            "creator": "Security Test Creator",
        },
    )
    assert response.status_code == 401


def test_task_creation_accepts_valid_api_key():
    response = client.post(
        "/api/tasks",
        headers=API_HEADERS,
        json={
            "video_url": "https://www.youtube.com/watch?v=securitytest",
            "creator": "Security Test Creator",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "queued"


def test_api_key_cannot_revoke_creator_authorization():
    channel_id = create_unapproved_channel()
    response = client.delete(
        f"/api/channels/{channel_id}/authorization",
        headers=API_HEADERS,
    )
    assert response.status_code == 401


def test_authorized_channel_stays_disabled_after_revocation():
    channel_id = create_unapproved_channel()
    approved = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=ADMIN_HEADERS,
    )
    assert approved.status_code == 200

    enabled = client.patch(
        f"/api/channels/{channel_id}?enabled=true",
        headers=API_HEADERS,
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    revoked = client.delete(
        f"/api/channels/{channel_id}/authorization",
        headers=ADMIN_HEADERS,
    )
    assert revoked.status_code == 200
    assert revoked.json()["authorized"] is False
    assert revoked.json()["enabled"] is False
