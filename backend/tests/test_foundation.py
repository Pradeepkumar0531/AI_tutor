"""Backend tests: startup, health, errors, request IDs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password, verify_password
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_app_starts_and_openapi_exposed(client: TestClient) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert res.json()["info"]["title"]


def test_health_liveness(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_readiness_reports_database(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert "database" in res.json()


def test_request_id_propagated(client: TestClient) -> None:
    res = client.get("/api/v1/health", headers={"X-Request-ID": "test-123"})
    assert res.status_code == 200
    assert res.headers["X-Request-ID"] == "test-123"


def test_request_id_generated_when_missing(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.headers.get("X-Request-ID")


def test_unknown_route_returns_envelope(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert "error" in res.json()
    assert "request_id" in res.json()["error"]


def test_password_hashing_argon2id() -> None:
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_roundtrip() -> None:
    token = create_access_token("user-1")
    from app.core.security import decode_access_token

    assert decode_access_token(token)["sub"] == "user-1"
