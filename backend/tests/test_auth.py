"""Authentication, authorization, and tenant-isolation tests over the real HTTP API.

The app under test uses the shared SQLite session fixture via a ``get_db``
dependency override, so every test exercises routes -> services -> repositories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.tokens import decode_access_token, issue_access_token
from app.core.config import Settings, get_settings
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.main import create_app
from app.models.ops import Event
from app.models.users import User


@pytest.fixture()
def client(session: Session) -> TestClient:
    app = create_app()

    def _override():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "SecurePass123") -> dict:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _login(client: TestClient, email: str, password: str = "SecurePass123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- registration


def test_register_valid_returns_token_and_safe_profile(client: TestClient) -> None:
    body = _register(client, "new@example.com")
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "new@example.com"
    assert "password_hash" not in body["user"]
    assert (
        "password_hash"
        not in client.post(
            "/api/v1/auth/register",
            json={"email": "x", "password": "y", "display_name": "z"},
        ).text
    )


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    _register(client, "dup@example.com")
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@example.com", "password": "SecurePass123", "display_name": "D"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_register_invalid_email_rejected(client: TestClient) -> None:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "SecurePass123", "display_name": "D"},
    )
    assert res.status_code == 422


def test_register_weak_passwords_rejected(client: TestClient) -> None:
    for bad in ["short", "   ", "", "1234567"]:
        res = client.post(
            "/api/v1/auth/register",
            json={"email": "w@example.com", "password": bad, "display_name": "D"},
        )
        assert res.status_code == 422, bad


def test_register_password_is_hashed(client: TestClient, session: Session) -> None:
    _register(client, "hash@example.com", password="SuperSecret123")
    user = session.query(User).filter_by(email="hash@example.com").one()
    assert user.password_hash != "SuperSecret123"
    assert verify_password("SuperSecret123", user.password_hash)
    assert not verify_password("WrongPassword123", user.password_hash)


# ---------------------------------------------------------------------- login


def test_login_correct_credentials(client: TestClient, session: Session) -> None:
    _register(client, "login@example.com")
    res = _login(client, "login@example.com")
    assert res.status_code == 200, res.text
    body = res.json()
    claims = decode_access_token(body["access_token"])
    assert claims["typ"] == "access"
    assert claims["sub"] == body["user"]["id"]
    assert "jti" in claims
    session.expire_all()
    user = session.query(User).filter_by(email="login@example.com").one()
    assert user.last_login_at is not None


def test_login_failures_are_generic(client: TestClient) -> None:
    _register(client, "known@example.com")
    wrong = _login(client, "known@example.com", password="WrongPassword123")
    unknown = _login(client, "nobody@example.com", password="WrongPassword123")
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    # Identical responses (request_id aside): no account enumeration.
    assert (
        wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == ("INVALID_CREDENTIALS")
    )
    assert (
        wrong.json()["error"]["message"]
        == unknown.json()["error"]["message"]
        == ("Invalid email or password.")
    )


def test_login_disabled_account_is_generic(client: TestClient, session: Session) -> None:
    _register(client, "off@example.com")
    user = session.query(User).filter_by(email="off@example.com").one()
    user.is_active = False
    session.commit()
    res = _login(client, "off@example.com")
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Invalid email or password."


def test_login_malformed_request(client: TestClient) -> None:
    res = client.post("/api/v1/auth/login", json={"email": "a@example.com"})
    assert res.status_code == 422


# ---------------------------------------------------------------------- tokens


def _signed(payload: dict, secret: str | None = None) -> str:
    settings = get_settings()
    return pyjwt.encode(payload, secret or settings.jwt_secret_key, algorithm="HS256")


def _base_payload(**over: object) -> dict:
    now = datetime.now(UTC)
    payload: dict = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    payload.update(over)
    return payload


def test_me_valid_token(client: TestClient) -> None:
    body = _register(client, "me@example.com")
    res = client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert res.status_code == 200, res.text
    profile = res.json()
    assert profile["email"] == "me@example.com"
    assert "password_hash" not in profile
    assert "is_active" not in profile


def test_me_unauthenticated_returns_401(client: TestClient) -> None:
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_rejects_bad_tokens(client: TestClient) -> None:
    cases = {
        "malformed": "not-a-token",
        "wrong-signature": _signed(_base_payload(), secret="wrong-secret"),
        "expired": _signed(
            _base_payload(exp=int((datetime.now(UTC) - timedelta(hours=1)).timestamp()))
        ),
        "wrong-type": _signed(_base_payload(typ="refresh")),
        "missing-sub": _signed({k: v for k, v in _base_payload().items() if k != "sub"}),
        "unknown-user": _signed(_base_payload()),
    }
    for name, token in cases.items():
        res = client.get("/api/v1/auth/me", headers=_auth(token))
        assert res.status_code == 401, name
        assert res.json()["error"]["code"] == "UNAUTHORIZED", name


def test_legacy_core_token_still_accepted(client: TestClient) -> None:
    from app.core.security import create_access_token

    body = _register(client, "legacy@example.com")
    legacy = create_access_token(body["user"]["id"])
    res = client.get("/api/v1/auth/me", headers=_auth(legacy))
    assert res.status_code == 200


def test_production_requires_real_jwt_secret() -> None:
    # NOTE: production Settings also require explicit CORS_ORIGINS (separate
    # guard, tested in test_security.py) — supplied here to isolate the JWT check.
    weak = Settings(
        app_env="production", jwt_secret_key="change-me-jwt", cors_origins="https://app.example.com"
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        issue_access_token(uuid.uuid4(), weak)
    strong = Settings(
        app_env="production", jwt_secret_key="x" * 40, cors_origins="https://app.example.com"
    )
    issued = issue_access_token(uuid.uuid4(), strong)
    assert issued["access_token"]


# ---------------------------------------------------------------------- logout


def test_logout_flow(client: TestClient, session: Session) -> None:
    body = _register(client, "bye@example.com")
    res = client.post("/api/v1/auth/logout", headers=_auth(body["access_token"]))
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    events = session.query(Event).all()
    types = {e.event_type for e in events}
    assert "USER_LOGOUT" in {t.value if hasattr(t, "value") else t for t in types}


def test_logout_without_token_is_401(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 401


# ------------------------------------------------------- authorization / IDOR


def _tenant(client: TestClient, email: str) -> dict:
    reg = _register(client, email)
    token = reg["access_token"]
    space = client.post(
        "/api/v1/spaces", headers=_auth(token), json={"name": f"{email} space"}
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": space["id"], "name": f"{email} project"},
    ).json()
    return {"token": token, "space": space, "project": project}


def test_cross_tenant_isolation_matrix(client: TestClient) -> None:
    a = _tenant(client, "a@example.com")
    b = _tenant(client, "b@example.com")

    # A -> A allowed, B -> B allowed.
    for t in (a, b):
        res = client.get(f"/api/v1/projects/{t['project']['id']}", headers=_auth(t["token"]))
        assert res.status_code == 200, res.text
        assert res.json()["name"] == res.json()["name"]
        mats = client.get(
            f"/api/v1/projects/{t['project']['id']}/materials", headers=_auth(t["token"])
        )
        assert mats.status_code == 200
        spaces = client.get("/api/v1/spaces", headers=_auth(t["token"]))
        assert spaces.status_code == 200
        assert spaces.json()["total"] == 1

    # A -> B and B -> A denied with 404 and zero data disclosure.
    for me, other in ((a, b), (b, a)):
        res = client.get(f"/api/v1/projects/{other['project']['id']}", headers=_auth(me["token"]))
        assert res.status_code == 404
        assert other["project"]["name"] not in res.text
        assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

        res = client.get(
            f"/api/v1/projects/{other['project']['id']}/materials",
            headers=_auth(me["token"]),
        )
        assert res.status_code == 404

        res = client.get(f"/api/v1/spaces/{other['space']['id']}", headers=_auth(me["token"]))
        assert res.status_code == 404
        assert other["space"]["name"] not in res.text


def test_unauthenticated_resource_access_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/spaces").status_code == 401
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}").status_code == 401
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}/materials").status_code == 401


def test_disabled_account_cannot_use_token(client: TestClient, session: Session) -> None:
    body = _register(client, "doomed@example.com")
    token = body["access_token"]
    user = session.query(User).filter_by(email="doomed@example.com").one()
    user.is_active = False
    session.commit()
    res = client.get("/api/v1/auth/me", headers=_auth(token))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCOUNT_DISABLED"


# ------------------------------------------------------------------ CORS


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    good = client.options(
        "/api/v1/spaces",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert good.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = client.options(
        "/api/v1/spaces",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in evil.headers


# ------------------------------------------------------------------ security


def test_no_secrets_or_hashes_leak(client: TestClient) -> None:
    body = _register(client, "leak@example.com")
    secret = get_settings().jwt_secret_key
    for text in [
        client.post(
            "/api/v1/auth/login",
            json={"email": "leak@example.com", "password": "SecurePass123"},
        ).text,
        client.get("/api/v1/auth/me", headers=_auth(body["access_token"])).text,
    ]:
        lowered = text.lower()
        assert "password_hash" not in lowered
        assert "argon" not in lowered
        assert secret not in text


def test_tokens_never_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    body = _register(client, "quiet@example.com")
    token = body["access_token"]
    with caplog.at_level(logging.INFO):
        client.get("/api/v1/auth/me", headers=_auth(token))
        client.get("/api/v1/spaces", headers=_auth(token))
    assert token not in caplog.text
    assert "Bearer" not in caplog.text


def test_password_policy_unit() -> None:
    from app.auth.password import validate_password

    assert validate_password("12345678") == "12345678"
    for bad in ["", "   ", "short", "x" * 129]:
        with pytest.raises(ValueError):
            validate_password(bad)
    assert hash_password("abc") != "abc"  # never plaintext
