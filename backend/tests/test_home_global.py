"""Home + global analytics: aggregation, isolation, honest cold start."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture()
def client(session: Session) -> TestClient:
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    def _override():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient, email: str) -> dict:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_home_cold_start_honest(client: TestClient) -> None:
    body = _register(client, "new@example.com")
    res = client.get("/api/v1/home", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    home = res.json()
    assert home["continue_learning"] is None
    assert home["recent_projects"] == []
    assert home["recommended_action"] is None
    assert home["progress"]["projects"] == 0
    assert home["attention"] == []


def test_global_summary_cold_start_honest(client: TestClient) -> None:
    body = _register(client, "new@example.com")
    res = client.get("/api/v1/analytics/summary", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["projects"] == 0 and summary["mastery_concepts"] == 0
    assert summary["attention"] == [] and summary["recent_project_ids"] == []


def test_home_and_summary_with_activity(client: TestClient) -> None:
    body = _register(client, "user@example.com")
    headers = _auth(body["access_token"])
    space = client.post("/api/v1/spaces", headers=headers, json={"name": "S"}).json()
    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"space_id": space["id"], "name": "P", "learning_goal": "Learn X"},
    ).json()

    res = client.get("/api/v1/home", headers=headers)
    assert res.status_code == 200, res.text
    home = res.json()
    assert home["continue_learning"]["project_id"] == project["id"]
    assert home["continue_learning"]["next_action"]["kind"] == "upload_material"
    assert home["continue_learning"]["next_action"]["project_id"] == project["id"]
    assert home["recommended_action"]["kind"] == "upload_material"
    assert home["recent_projects"][0]["id"] == project["id"]
    assert home["progress"]["projects"] == 1

    res = client.get("/api/v1/analytics/summary", headers=headers)
    summary = res.json()
    assert summary["projects"] == 1 and summary["materials"] == 0


def test_global_isolation_between_users(client: TestClient) -> None:
    alice = _register(client, "alice@example.com")
    bob = _register(client, "bob@example.com")
    space = client.post(
        "/api/v1/spaces", headers=_auth(alice["access_token"]), json={"name": "S"}
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=_auth(alice["access_token"]),
        json={"space_id": space["id"], "name": "P"},
    ).json()

    bob_home = client.get("/api/v1/analytics/summary", headers=_auth(bob["access_token"])).json()
    assert bob_home["projects"] == 0
    assert project["id"] not in bob_home["recent_project_ids"]

    alice_home = client.get(
        "/api/v1/analytics/summary", headers=_auth(alice["access_token"])
    ).json()
    assert alice_home["projects"] == 1


def test_home_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/home").status_code == 401
    assert client.get("/api/v1/analytics/summary").status_code == 401
