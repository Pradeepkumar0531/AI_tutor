"""Database connectivity failure diagnostics.

A DNS/connectivity failure (e.g. an unresolvable Postgres host) must surface
as a clear degraded readiness payload — never an unexplained 500, and never
with credentials or connection strings in responses or logs. These tests drive
the real ``check_database`` + ``/health/ready`` path against an unresolvable
host (RFC 2606 ``.invalid`` — no live infrastructure touched).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import session as session_module
from app.db.session import check_database, reset_engine_cache
from app.main import create_app

FAKE_URL = "postgresql+psycopg://probe_user:probe_password_123@unresolvable.invalid:5432/probe"


class _FakeSettings:
    database_url = FAKE_URL
    db_pool_size = 1
    db_max_overflow = 0
    db_pool_timeout_seconds = 5
    db_pool_recycle_seconds = 60


@pytest.fixture()
def unresolvable_db(monkeypatch):
    """Point the session layer at a host that can never resolve."""
    monkeypatch.setattr(session_module, "get_settings", lambda: _FakeSettings())
    reset_engine_cache()
    try:
        yield
    finally:
        reset_engine_cache()


def test_unresolvable_host_reports_degraded_safely(unresolvable_db) -> None:
    db = check_database()
    assert db["configured"] is True
    assert db["reachable"] is False
    assert db["error"] == "OperationalError"
    blob = repr(db)
    assert "probe_password_123" not in blob
    assert "probe_user" not in blob
    assert "unresolvable.invalid" not in blob


def test_readiness_endpoint_reports_degraded_not_500(unresolvable_db) -> None:
    res = TestClient(create_app()).get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is False
    assert body["database"]["reachable"] is False
    assert "probe_password_123" not in res.text
    assert FAKE_URL not in res.text


def test_login_maps_connectivity_failure_to_503(unresolvable_db) -> None:
    """End-to-end failure mapping: DB down during login -> safe 503 envelope
    with request ID, never a bare 500 and never secrets."""
    res = TestClient(create_app()).post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword123"},
    )
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["message"] == "The service is temporarily unavailable. Please try again."
    assert body["error"]["details"] is None
    assert body["error"]["request_id"]
    assert "probe_password_123" not in res.text
    assert FAKE_URL not in res.text


def test_driver_error_message_carries_no_credentials(unresolvable_db) -> None:
    import sqlalchemy as sa
    from sqlalchemy.exc import OperationalError

    engine = sa.create_engine(FAKE_URL)
    try:
        with pytest.raises(OperationalError) as exc_info:
            with engine.connect():
                pass
        message = str(exc_info.value)
        assert "probe_password_123" not in message
        assert "probe_user@" not in message
    finally:
        engine.dispose()
