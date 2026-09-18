"""Admin RBAC + endpoints: server-side gating, secret-free aggregates.

Covers: learner→403, anon→401, disabled→403, unknown→401, bootstrap
promotion on register/login, overview/users/journey/activity/jobs/health/
ai-usage/evaluations, pagination, filters, and no-secret responses.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import config as config_module


@pytest.fixture()
def client(session: Session, monkeypatch) -> TestClient:
    from app.db.session import get_db
    from app.main import create_app

    config_module.get_settings.cache_clear()
    app = create_app()

    def _override():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, raise_server_exceptions=False)
    config_module.get_settings.cache_clear()


@pytest.fixture()
def admin_emails(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


def _register(client: TestClient, email: str) -> dict:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    body = _register(client, "boss@example.com")
    assert body["user"]["role"] == "admin"
    return body["access_token"]


# ------------------------------------------------------------- RBAC matrix


def test_learner_denied_admin_overview(client: TestClient) -> None:
    body = _register(client, "learner@example.com")
    assert body["user"]["role"] == "learner"
    res = client.get("/api/v1/admin/overview", headers=_auth(body["access_token"]))
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_anonymous_denied_admin(client: TestClient) -> None:
    res = client.get("/api/v1/admin/overview")
    assert res.status_code == 401


def test_admin_allowed_overview(client: TestClient, admin_emails) -> None:
    token = _admin_token(client)
    res = client.get("/api/v1/admin/overview", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    for key in (
        "users",
        "spaces",
        "projects",
        "materials",
        "assessments",
        "tutor_conversations",
        "active_recommendations",
        "events",
        "ai_calls",
        "evaluation_runs",
        "jobs",
    ):
        assert key in body, key
    assert body["users"] >= 1


def test_bootstrap_on_login_for_existing_user(
    client: TestClient, session: Session, admin_emails, monkeypatch
) -> None:
    body = _register(client, "boss@example.com")
    assert body["user"]["role"] == "admin"
    # Existing learner promoted at next login once listed.
    plain = _register(client, "late@example.com")
    assert plain["user"]["role"] == "learner"
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com,late@example.com")
    config_module.get_settings.cache_clear()
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "late@example.com", "password": "SecurePass123"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "admin"


def test_disabled_admin_denied(client: TestClient, session: Session, admin_emails) -> None:
    from app.models.users import User

    token = _admin_token(client)
    user = session.query(User).filter_by(email="boss@example.com").one()
    user.is_active = False
    session.commit()
    res = client.get("/api/v1/admin/overview", headers=_auth(token))
    assert res.status_code == 403


def test_unknown_user_token_denied(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from app.core.config import get_settings

    token = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "jti": uuid.uuid4().hex,
        },
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    res = client.get("/api/v1/admin/overview", headers=_auth(token))
    assert res.status_code == 401


def test_learner_cannot_inspect_users(client: TestClient) -> None:
    body = _register(client, "learner@example.com")
    res = client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=_auth(body["access_token"]))
    assert res.status_code == 403


# ------------------------------------------------------------- users + journey


def test_users_list_and_journey(client: TestClient, session: Session, admin_emails) -> None:
    token = _admin_token(client)
    learner = _register(client, "learner@example.com")
    res = client.get("/api/v1/admin/users?limit=5", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 2 and len(body["items"]) <= 5
    assert "password_hash" not in res.text
    for u in body["items"]:
        assert set(u) <= {
            "id",
            "email",
            "display_name",
            "role",
            "is_active",
            "last_login_at",
            "created_at",
        }
    uid = learner["user"]["id"]
    res = client.get(f"/api/v1/admin/users/{uid}", headers=_auth(token))
    assert res.status_code == 200, res.text
    journey = res.json()
    assert journey["user"]["email"] == "learner@example.com"
    assert journey["project_ids"] == []
    assert journey["mastery_concepts"] == 0
    res = client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=_auth(token))
    assert res.status_code == 404


# ------------------------------------------------------------- activity + jobs


def test_activity_filters(client: TestClient, session: Session, admin_emails) -> None:
    token = _admin_token(client)
    learner = _register(client, "learner@example.com")
    space = client.post(
        "/api/v1/spaces", headers=_auth(learner["access_token"]), json={"name": "S"}
    ).json()
    res = client.get(
        f"/api/v1/admin/activity?user_id={learner['user']['id']}&event_type=SPACE_CREATED",
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["total"] >= 1
    res = client.get(
        "/api/v1/admin/activity?event_type=NOPE_NOT_A_TYPE",
        headers=_auth(token),
    )
    assert res.status_code == 200 and res.json()["total"] == 0
    res = client.get(
        f"/api/v1/admin/activity?space_id={space['id']}",
        headers=_auth(token),
    )
    assert res.json()["total"] >= 1


def test_jobs_visible_after_upload(
    client: TestClient, session: Session, admin_emails, tmp_path
) -> None:
    from tests.pdf_fixtures import make_text_pdf

    token = _admin_token(client)
    learner = _register(client, "learner@example.com")
    space = client.post(
        "/api/v1/spaces", headers=_auth(learner["access_token"]), json={"name": "S"}
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=_auth(learner["access_token"]),
        json={"space_id": space["id"], "name": "P"},
    ).json()
    pdf = make_text_pdf(["hello there, learning"])
    res = client.post(
        f"/api/v1/projects/{project['id']}/materials",
        headers=_auth(learner["access_token"]),
        files={"file": ("n.pdf", pdf, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    res = client.get("/api/v1/admin/jobs", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    job = body["items"][0]
    assert job["job_type"] and job["status"] in (
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "RETRYING",
    )
    assert "password" not in res.text.lower()
    res = client.get("/api/v1/admin/jobs?status=QUEUED", headers=_auth(token))
    assert res.status_code == 200


# ------------------------------------------------------------- health + ai + eval


def test_health_secret_free(client: TestClient, admin_emails) -> None:
    token = _admin_token(client)
    res = client.get("/api/v1/admin/health", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["overall"] in ("healthy", "degraded")
    assert body["api"] == "healthy"
    for secret in ("gsk_", "AIza", "BEGIN", "postgresql://", "rediss://"):
        assert secret not in res.text
    assert isinstance(body["ai"].get("groq_configured"), bool)


def test_ai_usage_empty_then_recorded(client: TestClient, session: Session, admin_emails) -> None:
    from app.services.ai_usage_service import AiUsageService

    token = _admin_token(client)
    res = client.get("/api/v1/admin/ai-usage/summary", headers=_auth(token))
    assert res.status_code == 200 and res.json() == []
    learner = _register(client, "learner@example.com")
    AiUsageService(session).record(
        feature="tutor",
        provider="groq",
        model="openai/gpt-oss-20b",
        latency_ms=120,
        user_id=uuid.UUID(learner["user"]["id"]),
        input_tokens=100,
        output_tokens=50,
    )
    session.commit()
    res = client.get("/api/v1/admin/ai-usage/summary", headers=_auth(token))
    assert res.status_code == 200, res.text
    row = res.json()[0]
    assert row["feature"] == "tutor" and row["requests"] == 1
    assert row["input_tokens"] == 100 and row["failures"] == 0
    res = client.get("/api/v1/admin/ai-usage?feature=tutor", headers=_auth(token))
    assert res.json()["total"] == 1


def test_evaluations_run_and_summary(client: TestClient, admin_emails) -> None:
    token = _admin_token(client)
    res = client.get("/api/v1/admin/evaluations/summary", headers=_auth(token))
    assert res.status_code == 200 and res.json() is None
    res = client.post("/api/v1/admin/evaluations/run", headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_cases"] == 16 and body["failed"] == 0
    res = client.get("/api/v1/admin/evaluations/summary", headers=_auth(token))
    summary = res.json()
    assert summary["total"] == 16 and summary["passed"] == 16
    assert {c["category"] for c in summary["by_category"]} == {
        "tutor",
        "retrieval",
        "assessment",
        "recommendations",
    }
    learner = _register(client, "learner@example.com")
    res = client.post("/api/v1/admin/evaluations/run", headers=_auth(learner["access_token"]))
    assert res.status_code == 403
