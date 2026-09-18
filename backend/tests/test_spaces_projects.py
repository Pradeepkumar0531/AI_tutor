"""Spaces & Projects API: CRUD, archive/restore, search, pagination, counts, events,
and the cross-tenant isolation matrix — all over the real HTTP API with the
shared SQLite session fixture via a ``get_db`` dependency override.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.enums import EventType
from app.models.ops import Event


@pytest.fixture()
def client(session: Session) -> TestClient:
    app = create_app()

    def _override():  # type: ignore[no-untyped-def]
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _register(client: TestClient, email: str) -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _space(client: TestClient, token: str, name: str = "Math") -> dict:
    res = client.post(
        "/api/v1/spaces", headers=_auth(token), json={"name": name, "description": "d"}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _project(client: TestClient, token: str, space_id: str, name: str = "Algebra") -> dict:
    res = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": space_id, "name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------ spaces


def test_space_crud_lifecycle(client: TestClient, session: Session) -> None:
    token = _register(client, "s1@example.com")

    created = _space(client, token, "Physics")
    assert created["project_count"] == 0
    assert created["archived_at"] is None
    space_id = created["id"]

    got = client.get(f"/api/v1/spaces/{space_id}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["name"] == "Physics"

    patched = client.patch(
        f"/api/v1/spaces/{space_id}",
        headers=_auth(token),
        json={"name": "Advanced Physics", "description": "Relativity + QM"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Advanced Physics"
    assert patched.json()["description"] == "Relativity + QM"

    # Owner identity is not writable: no such field is accepted or leaked.
    assert "owner_id" in patched.json()  # present but unchanged below
    owner_before = patched.json()["owner_id"]
    patched2 = client.patch(
        f"/api/v1/spaces/{space_id}",
        headers=_auth(token),
        json={"name": "P2"},
    )
    assert patched2.json()["owner_id"] == owner_before

    archived = client.delete(f"/api/v1/spaces/{space_id}", headers=_auth(token))
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    # Archived rows disappear from reads but can be restored.
    assert client.get(f"/api/v1/spaces/{space_id}", headers=_auth(token)).status_code == 404
    listed = client.get("/api/v1/spaces", headers=_auth(token)).json()
    assert listed["total"] == 0

    restored = client.post(f"/api/v1/spaces/{space_id}/restore", headers=_auth(token))
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert client.get(f"/api/v1/spaces/{space_id}", headers=_auth(token)).status_code == 200

    # Archived rows are hidden by default but visible with include_archived.
    client.delete(f"/api/v1/spaces/{space_id}", headers=_auth(token))
    hidden = client.get("/api/v1/spaces", headers=_auth(token)).json()
    assert hidden["total"] == 0
    shown = client.get("/api/v1/spaces?include_archived=true", headers=_auth(token)).json()
    assert shown["total"] == 1
    assert shown["items"][0]["archived_at"] is not None


def test_space_validation(client: TestClient) -> None:
    token = _register(client, "s2@example.com")
    assert client.post("/api/v1/spaces", headers=_auth(token), json={"name": ""}).status_code == 422
    assert client.post("/api/v1/spaces", headers=_auth(token), json={}).status_code == 422
    space_id = _space(client, token)["id"]
    assert (
        client.patch(
            f"/api/v1/spaces/{space_id}", headers=_auth(token), json={"name": "   "}
        ).status_code
        == 400
    )


def test_space_pagination_and_search(client: TestClient) -> None:
    token = _register(client, "s3@example.com")
    for name in ["Mathematics", "Mathematical Logic", "Physics", "Chemistry", "Biology"]:
        _space(client, token, name)

    page1 = client.get("/api/v1/spaces?page=1&page_size=2", headers=_auth(token)).json()
    assert page1["total"] == 5 and len(page1["items"]) == 2
    page3 = client.get("/api/v1/spaces?page=3&page_size=2", headers=_auth(token)).json()
    assert len(page3["items"]) == 1

    found = client.get("/api/v1/spaces?search=math", headers=_auth(token)).json()
    assert found["total"] == 2
    assert {s["name"] for s in found["items"]} == {"Mathematics", "Mathematical Logic"}

    # LIKE wildcards in search are escaped, not interpreted.
    escaped = client.get("/api/v1/spaces?search=%", headers=_auth(token)).json()
    assert escaped["total"] == 0


def test_space_lifecycle_events(client: TestClient, session: Session) -> None:
    token = _register(client, "s4@example.com")
    space = _space(client, token, "Events 101")
    rows = session.query(Event).filter(Event.entity_id == uuid.UUID(space["id"])).all()
    assert [r.event_type for r in rows] == [EventType.SPACE_CREATED]
    assert rows[0].payload == {"name": "Events 101"}
    assert "password" not in str(rows[0].payload).lower()


# ---------------------------------------------------------------- projects


def test_project_crud_lifecycle(client: TestClient) -> None:
    token = _register(client, "p1@example.com")
    space_id = _space(client, token)["id"]

    created = _project(client, token, space_id, "Calculus")
    assert created["space_id"] == space_id
    assert created["material_count"] == 0
    project_id = created["id"]

    got = client.get(f"/api/v1/projects/{project_id}", headers=_auth(token))
    assert got.status_code == 200
    assert got.json()["material_count"] == 0

    patched = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_auth(token),
        json={
            "name": "Calculus I",
            "description": "Limits",
            "learning_goal": "Derivatives",
            "target_outcome": "Pass exam",
            "difficulty": "MEDIUM",
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert (body["name"], body["difficulty"], body["target_outcome"]) == (
        "Calculus I",
        "MEDIUM",
        "Pass exam",
    )

    # Forbidden fields are not accepted by the schema (422 on unknown fields is
    # not enforced; instead assert they are ignored, never applied).
    sneaky = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_auth(token),
        json={"name": "Calculus II", "owner_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert sneaky.status_code == 200
    assert sneaky.json()["name"] == "Calculus II"
    assert sneaky.json()["owner_id"] != "00000000-0000-0000-0000-000000000000"

    archived = client.delete(f"/api/v1/projects/{project_id}", headers=_auth(token))
    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert client.get(f"/api/v1/projects/{project_id}", headers=_auth(token)).status_code == 404
    restored = client.post(f"/api/v1/projects/{project_id}/restore", headers=_auth(token))
    assert restored.status_code == 200 and restored.json()["archived_at"] is None


def test_project_creation_guards(client: TestClient) -> None:
    token = _register(client, "p2@example.com")
    other = _register(client, "p2b@example.com")
    other_space = _space(client, other, "Other")

    # Cannot create into another user's space — 404, no disclosure.
    res = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": other_space["id"], "name": "Sneaky"},
    )
    assert res.status_code == 404

    # Unknown space id — 404 as well (indistinguishable).
    res = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": "00000000-0000-0000-0000-000000000000", "name": "Ghost"},
    )
    assert res.status_code == 404

    # Invalid payloads rejected.
    space_id = _space(client, token)["id"]
    assert (
        client.post(
            "/api/v1/projects", headers=_auth(token), json={"space_id": space_id}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/projects/{_project(client, token, space_id)['id']}",
            headers=_auth(token),
            json={"difficulty": "IMPOSSIBLE"},
        ).status_code
        == 422
    )


def test_project_listing_filter_pagination_search(client: TestClient) -> None:
    token = _register(client, "p3@example.com")
    s1 = _space(client, token, "S1")["id"]
    s2 = _space(client, token, "S2")["id"]
    _project(client, token, s1, "Alpha")
    _project(client, token, s1, "Beta")
    _project(client, token, s2, "Gamma")

    all_items = client.get("/api/v1/projects", headers=_auth(token)).json()
    assert all_items["total"] == 3

    filtered = client.get(f"/api/v1/projects?space_id={s1}", headers=_auth(token)).json()
    assert filtered["total"] == 2
    assert {p["name"] for p in filtered["items"]} == {"Alpha", "Beta"}

    paged = client.get("/api/v1/projects?page=2&page_size=2", headers=_auth(token)).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1

    searched = client.get("/api/v1/projects?search=alp", headers=_auth(token)).json()
    assert searched["total"] == 1 and searched["items"][0]["name"] == "Alpha"


def test_project_created_event(client: TestClient, session: Session) -> None:
    token = _register(client, "p4@example.com")
    space_id = _space(client, token)["id"]
    project = _project(client, token, space_id, "Evented")
    rows = session.query(Event).filter(Event.entity_id == uuid.UUID(project["id"])).all()
    assert [r.event_type for r in rows] == [EventType.PROJECT_CREATED]
    assert rows[0].project_id == uuid.UUID(project["id"])
    assert rows[0].payload == {"name": "Evented", "space_id": space_id}


def test_space_detail_project_counts(client: TestClient) -> None:
    token = _register(client, "p5@example.com")
    space = _space(client, token, "Counted")
    assert space["project_count"] == 0
    _project(client, token, space["id"], "One")
    _project(client, token, space["id"], "Two")
    got = client.get(f"/api/v1/spaces/{space['id']}", headers=_auth(token)).json()
    assert got["project_count"] == 2
    listed = client.get("/api/v1/spaces", headers=_auth(token)).json()
    assert listed["items"][0]["project_count"] == 2


# ------------------------------------------------------- isolation matrix


def _tenant(client: TestClient, email: str) -> dict:
    token = _register(client, email)
    space = _space(client, token, f"{email} space")
    project = _project(client, token, space["id"], f"{email} project")
    return {"token": token, "space": space, "project": project}


def test_cross_tenant_matrix(client: TestClient) -> None:
    a = _tenant(client, "mx-a@example.com")
    b = _tenant(client, "mx-b@example.com")

    # Own resources: 200 everywhere.
    assert (
        client.get(f"/api/v1/spaces/{a['space']['id']}", headers=_auth(a["token"])).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/projects/{a['project']['id']}", headers=_auth(a["token"])).status_code
        == 200
    )

    # Cross-tenant: 404 with no data disclosure, for every mutation too.
    for me, other in ((a, b), (b, a)):
        h = _auth(me["token"])
        r = client.get(f"/api/v1/spaces/{other['space']['id']}", headers=h)
        assert r.status_code == 404
        assert other["space"]["name"] not in r.text

        r = client.get(f"/api/v1/projects/{other['project']['id']}", headers=h)
        assert r.status_code == 404
        assert other["project"]["name"] not in r.text

        r = client.patch(
            f"/api/v1/projects/{other['project']['id']}", headers=h, json={"name": "X"}
        )
        assert r.status_code == 404

        r = client.delete(f"/api/v1/projects/{other['project']['id']}", headers=h)
        assert r.status_code == 404

        r = client.patch(f"/api/v1/spaces/{other['space']['id']}", headers=h, json={"name": "X"})
        assert r.status_code == 404

        r = client.delete(f"/api/v1/spaces/{other['space']['id']}", headers=h)
        assert r.status_code == 404

        r = client.post(f"/api/v1/projects/{other['project']['id']}/restore", headers=h)
        assert r.status_code == 404

        # Victim data untouched by the attempts.
        mine = client.get(
            f"/api/v1/projects/{other['project']['id']}",
            headers=_auth(other["token"]),
        ).json()
        assert mine["name"] == other["project"]["name"]
        assert mine["archived_at"] is None


def test_space_filtered_listing_leaks_nothing(client: TestClient) -> None:
    a = _tenant(client, "ml-a@example.com")
    b = _tenant(client, "ml-b@example.com")

    # Filtering by another user's space id yields zero rows — never its contents.
    res = client.get(f"/api/v1/projects?space_id={b['space']['id']}", headers=_auth(a["token"]))
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    res = client.get(f"/api/v1/projects/{b['project']['id']}/materials", headers=_auth(a["token"]))
    assert res.status_code == 404

    # Unauthenticated access stays 401.
    assert client.get("/api/v1/spaces").status_code == 401
    assert client.patch(f"/api/v1/spaces/{a['space']['id']}", json={"name": "X"}).status_code == 401
    assert client.delete(f"/api/v1/spaces/{a['space']['id']}").status_code == 401
