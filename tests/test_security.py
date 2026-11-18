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
        json={"proof_reference": "creator-email-approval-001"},
    )
    assert response.status_code == 401


def test_admin_can_authorize_and_revoke_creator():
    channel_id = create_unapproved_channel()

    approved = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=ADMIN_HEADERS,
        json={"proof_reference": "creator-email-approval-001"},
    )
    assert approved.status_code == 200
    assert approved.json()["authorized"] is True
    assert approved.json()["authorization_proof"] == "creator-email-approval-001"
    assert approved.json()["authorized_at"] is not None

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
        json={"proof_reference": "creator-email-approval-002"},
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


def test_admin_cannot_authorize_without_permission_evidence():
    channel_id = create_unapproved_channel()
    response = client.post(
        f"/api/channels/{channel_id}/authorize",
        headers=ADMIN_HEADERS,
        json={"proof_reference": "no"},
    )
    assert response.status_code == 422


# Task lifecycle tests
os.environ["CLIPFORGE_WORKER_KEY"] = "test-worker-key"
WORKER_HEADERS = {"X-Worker-Key": "test-worker-key"}


def create_task():
    response = client.post(
        "/api/tasks",
        headers=API_HEADERS,
        json={"video_url": "https://www.youtube.com/watch?v=workflowtest", "creator": "Approved Test Creator"},
    )
    assert response.status_code == 201
    return response.json()


def test_task_lifecycle_claim_complete():
    created = create_task()
    assert created["status"] == "queued"
    assert created["attempt_count"] == 0

    claimed = client.post(
        "/api/worker/tasks/claim?worker_id=worker-test",
        headers=WORKER_HEADERS,
    )
    assert claimed.status_code == 200
    task = claimed.json()["task"]
    assert task["id"] == created["id"]
    assert task["status"] == "processing"
    assert task["attempt_count"] == 1
    assert task["worker_id"] == "worker-test"
    assert task["started_at"] is not None

    completed = client.post(
        f"/api/worker/tasks/{created['id']}/complete",
        headers=WORKER_HEADERS,
        json={"result_reference": "drive://clip-output-001"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["finished_at"] is not None


def test_worker_endpoints_require_worker_key():
    response = client.post("/api/worker/tasks/claim")
    assert response.status_code == 401


def test_worker_cannot_complete_unclaimed_task():
    created = create_task()
    response = client.post(
        f"/api/worker/tasks/{created['id']}/complete",
        headers=WORKER_HEADERS,
        json={},
    )
    assert response.status_code == 409


def test_failed_task_can_be_retried_and_claimed_again():
    created = create_task()
    claimed = client.post("/api/worker/tasks/claim", headers=WORKER_HEADERS).json()["task"]
    failed = client.post(
        f"/api/worker/tasks/{created['id']}/fail",
        headers=WORKER_HEADERS,
        json={"error_message": "Temporary worker error"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_message"] == "Temporary worker error"

    retried = client.post(f"/api/tasks/{created['id']}/retry", headers=API_HEADERS)
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["error_message"] is None

    claimed_again = client.post("/api/worker/tasks/claim", headers=WORKER_HEADERS).json()["task"]
    assert claimed_again["id"] == created["id"]
    assert claimed_again["attempt_count"] == 2


def test_task_retry_rejects_non_failed_task():
    created = create_task()
    response = client.post(f"/api/tasks/{created['id']}/retry", headers=API_HEADERS)
    assert response.status_code == 409


def test_task_list_supports_status_filter_and_pagination():
    created = create_task()
    response = client.get("/api/tasks?status=queued&limit=10&offset=0", headers=API_HEADERS)
    assert response.status_code == 200
    assert any(task["id"] == created["id"] for task in response.json())
