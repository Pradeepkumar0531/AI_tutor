"""Materials: upload validation, storage, upload API, authz, lifecycle routes."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.documents.validation import (
    UploadTooLargeError,
    UploadValidationError,
    build_storage_key,
    validate_pdf_upload,
)
from app.main import create_app
from app.models.enums import EventType, MaterialStatus
from app.models.materials import Material
from app.models.ops import Event
from app.storage import LocalStorage, NeonObjectStorage, StorageError, StorageService
from tests.pdf_fixtures import LOREM, make_not_a_pdf, make_text_pdf

PDF = make_text_pdf([LOREM, LOREM + " Second page here."])


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):
    """Never touch a real broker in route tests: dispatch is a separately
    tested contract (see test_dispatch_*); here it always 'succeeds'."""
    import app.api.routes.materials as routes

    monkeypatch.setattr(routes, "dispatch_processing", lambda _mid: True)


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Route all service storage writes to an isolated tmp dir."""
    import app.services.material_service as svc

    backend = LocalStorage(root=str(tmp_path / "storage"))
    monkeypatch.setattr(
        svc, "get_storage_service", lambda: StorageService(backend, provider="local")
    )
    return backend


@pytest.fixture()
def client(session: Session, isolated_storage) -> TestClient:
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


def _upload(client, token, project_id, data=PDF, filename="notes.pdf", title=None):
    files = {"file": (filename, data, "application/pdf")}
    form = {"title": title} if title else {}
    return client.post(
        f"/api/v1/projects/{project_id}/materials",
        headers=_auth(token),
        files=files,
        data=form,
    )


@pytest.fixture()
def tenant(client: TestClient):
    token = _register(client, "author@example.com")
    space = client.post("/api/v1/spaces", headers=_auth(token), json={"name": "S"}).json()
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": space["id"], "name": "P"},
    ).json()
    return {"token": token, "project_id": project["id"]}


# ------------------------------------------------------------ validation

VALID_KWARGS = dict(filename="notes.pdf", content_type="application/pdf", max_bytes=100_000)


def test_validation_accepts_real_pdf() -> None:
    v = validate_pdf_upload(data=PDF, **VALID_KWARGS)
    assert v.size_bytes == len(PDF) and len(v.sha256) == 64
    assert v.content_type == "application/pdf"


def test_validation_rejects_empty() -> None:
    with pytest.raises(UploadValidationError, match="empty"):
        validate_pdf_upload(data=b"", **VALID_KWARGS)


def test_validation_rejects_oversize() -> None:
    with pytest.raises(UploadTooLargeError) as e:
        validate_pdf_upload(data=PDF, **{**VALID_KWARGS, "max_bytes": 10})
    assert e.value.status_code == 413


def test_validation_rejects_bad_extension_mime_and_magic() -> None:
    with pytest.raises(UploadValidationError):
        validate_pdf_upload(
            data=PDF, filename="notes.txt", content_type="application/pdf", max_bytes=100_000
        )
    with pytest.raises(UploadValidationError):
        validate_pdf_upload(
            data=PDF, filename="notes.pdf", content_type="image/png", max_bytes=100_000
        )
    with pytest.raises(UploadValidationError):
        validate_pdf_upload(data=make_not_a_pdf(), **VALID_KWARGS)


def test_validation_tolerates_missing_name_and_type() -> None:
    v = validate_pdf_upload(data=PDF, filename=None, content_type=None, max_bytes=100_000)
    assert v.filename == "document.pdf"


def test_storage_key_is_server_generated_and_safe() -> None:
    key = build_storage_key(project_id=uuid.uuid4(), material_id=uuid.uuid4())
    assert key.startswith("projects/") and key.endswith("/original.pdf")
    assert ".." not in key and "\\" not in key and " " not in key


# ------------------------------------------------------------ storage


def test_local_storage_roundtrip_and_traversal(tmp_path) -> None:
    backend = LocalStorage(root=str(tmp_path))
    backend.save("a/b/c.pdf", b"data")
    assert backend.load("a/b/c.pdf") == b"data"
    assert backend.exists("a/b/c.pdf") and not backend.exists("nope.pdf")
    backend.delete("a/b/c.pdf")
    assert not backend.exists("a/b/c.pdf")
    for evil in ["../evil.pdf", "/abs.pdf", "a\\b.pdf", "a\x00b.pdf"]:
        with pytest.raises(StorageError):
            backend.save(evil, b"x")


def test_neon_requires_configuration() -> None:
    with pytest.raises(StorageError, match="[Cc]onfigured"):
        NeonObjectStorage(endpoint="", access_key_id="", secret_access_key="", bucket_name="")
    with pytest.raises(StorageError, match="[Cc]onfigured"):
        NeonObjectStorage(
            endpoint="https://example.storage.neon.example",
            access_key_id="",
            secret_access_key="",
            bucket_name="",
        )


def _neon_storage(monkeypatch, client) -> NeonObjectStorage:
    """Neon provider with a mocked S3 transport (no credentials, no network).

    Mocked verification only: this proves the S3-compatible protocol usage
    (put/get/head/delete + error mapping), not a live Neon bucket.
    """
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    return NeonObjectStorage(
        endpoint="https://example.storage.neon.example",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket_name="test-bucket",
    )


def _client_error(code: str, status: int):
    from botocore.exceptions import ClientError

    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "TestOp",
    )


def test_neon_s3_put_get_delete(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from app.storage import ObjectNotFoundError

    store: dict[str, bytes] = {}
    client = MagicMock()
    client.put_object.side_effect = lambda Bucket, Key, Body, ContentType: store.update({Key: Body})
    body = MagicMock()
    body.read.return_value = b"data"
    client.get_object.side_effect = lambda Bucket, Key: (
        {"Body": body} if Key in store else (_ for _ in ()).throw(_client_error("NoSuchKey", 404))
    )
    client.delete_object.side_effect = lambda Bucket, Key: store.pop(Key, None)

    backend = _neon_storage(monkeypatch, client)
    assert backend.save("a/b.pdf", b"data", "application/pdf") == "a/b.pdf"
    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket" and kwargs["Key"] == "a/b.pdf"
    assert kwargs["Body"] == b"data" and kwargs["ContentType"] == "application/pdf"
    assert backend.load("a/b.pdf") == b"data"
    backend.delete("a/b.pdf")
    with pytest.raises(ObjectNotFoundError):
        backend.load("a/b.pdf")


def test_neon_exists_and_transient_errors(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from app.storage import ObjectNotFoundError

    client = MagicMock()
    client.head_object.side_effect = [True, _client_error("NoSuchKey", 404)]
    backend = _neon_storage(monkeypatch, client)
    assert backend.exists("a.pdf") is True
    assert backend.exists("missing.pdf") is False

    client.head_object.side_effect = _client_error("InternalError", 500)
    with pytest.raises(StorageError, match="transient"):
        backend.exists("a.pdf")

    client.get_object.side_effect = _client_error("AccessDenied", 403)
    with pytest.raises(StorageError):
        try:
            backend.load("a.pdf")
        except ObjectNotFoundError:
            pytest.fail("4xx must not map to ObjectNotFoundError")

    for evil in ["../evil.pdf", "/abs.pdf"]:
        with pytest.raises(StorageError):
            backend.save(evil, b"x")


def test_neon_provider_selection(monkeypatch) -> None:
    import app.core.config as config_module
    import app.storage.service as storage_module
    from app.core.config import Settings

    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: Settings(
            storage_backend="neon",
            neon_storage_endpoint="",
            neon_storage_access_key_id="",
            neon_storage_secret_access_key="",
            neon_storage_bucket_name="",
        ),
    )
    # Production must fail clearly, never silently fall back to local disk.
    with pytest.raises(StorageError, match="[Cc]onfigured"):
        storage_module.get_storage_service()

    from unittest.mock import MagicMock

    import boto3

    import app.storage.service as sm

    client = MagicMock()
    client.put_object.return_value = {}
    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: Settings(
            storage_backend="neon",
            neon_storage_endpoint="https://example.storage.neon.example",
            neon_storage_access_key_id="k",
            neon_storage_secret_access_key="s",
            neon_storage_bucket_name="b",
        ),
    )
    svc = sm.get_storage_service()
    assert svc.provider == "neon"
    assert svc.put("k.pdf", b"x") == "k.pdf"


# ------------------------------------------------------------ upload API


def test_upload_happy_path(client: TestClient, session: Session, tenant) -> None:
    res = _upload(client, tenant["token"], tenant["project_id"], title="My Notes")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "My Notes"
    assert body["status"] == "QUEUED"
    assert body["original_filename"] == "notes.pdf"
    assert body["file_size"] == len(PDF)
    assert "storage_key" not in body and "checksum" not in body

    mat = session.get(Material, uuid.UUID(body["id"]))
    assert mat is not None and mat.storage_key is not None
    assert mat.storage_key.startswith(f"projects/{tenant['project_id'].replace('-', '')}/")
    assert mat.retry_count == 0 and mat.processing_error is None

    from app.models.ops import ProcessingJob

    job = session.query(ProcessingJob).filter_by(material_id=mat.id).one()
    assert job.status.value == "QUEUED"
    assert job.idempotency_key == f"material:{mat.id}:process"

    events = session.query(Event).filter(Event.entity_id == mat.id).all()
    assert [e.event_type for e in events] == [EventType.MATERIAL_UPLOADED]


def test_upload_rejects_bad_files(client: TestClient, tenant) -> None:
    res = _upload(client, tenant["token"], tenant["project_id"], data=make_not_a_pdf())
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_UPLOAD"
    res = _upload(client, tenant["token"], tenant["project_id"], data=b"")
    assert res.status_code == 400
    res = _upload(client, tenant["token"], tenant["project_id"], data=PDF, filename="notes.txt")
    assert res.status_code == 400


def test_upload_enforces_authz(client: TestClient, tenant) -> None:
    other = _register(client, "other@example.com")
    res = _upload(client, other, tenant["project_id"])
    assert res.status_code == 404
    assert (
        client.post(
            f"/api/v1/projects/{tenant['project_id']}/materials",
            files={"file": ("n.pdf", PDF, "application/pdf")},
        ).status_code
        == 401
    )
    # Path traversal in the filename cannot escape the storage root.
    res = _upload(client, tenant["token"], tenant["project_id"], filename="../../evil.pdf")
    assert res.status_code == 201
    assert res.json()["original_filename"] == "evil.pdf"


def test_upload_rolls_back_and_cleans_storage(
    client, tenant, monkeypatch, isolated_storage, session
) -> None:
    """Mid-transaction DB failure after the object write -> compensating delete."""
    import app.services.material_service as svc

    def boom(*args, **kwargs):
        raise RuntimeError("simulated job-enqueue failure")

    monkeypatch.setattr(svc.ProcessingJobRepository, "enqueue", boom)
    res = _upload(client, tenant["token"], tenant["project_id"])
    assert res.status_code == 500, res.text
    # Object removed...
    leftovers = [p for p in isolated_storage.root.rglob("*") if p.is_file()]
    assert leftovers == []
    # ...no material row survived the rollback...
    assert session.query(Material).count() == 0
    # ...and the request surfaced a clean envelope, not a traceback.
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"


# ------------------------------------------------------------ reads


def _ready_material(client, tenant, session, name="Doc"):
    """Upload then run the real pipeline synchronously in-test (no broker)."""
    import app.services.material_service as svc
    from app.core.config import get_settings
    from app.documents.ocr import NullOcrProvider
    from app.jobs.document_tasks import execute_material_processing

    res = _upload(client, tenant["token"], tenant["project_id"], title=name)
    assert res.status_code == 201, res.text
    mid = uuid.UUID(res.json()["id"])
    out = execute_material_processing(
        mid,
        session=session,
        settings=get_settings(),
        storage=svc.get_storage_service(),
        ocr_provider_factory=NullOcrProvider,
    )
    assert out["status"] == "READY", out
    session.expire_all()
    return mid


def test_material_detail_and_counts(client: TestClient, session, tenant) -> None:
    mid = _ready_material(client, tenant, session)
    res = client.get(
        f"/api/v1/projects/{tenant['project_id']}/materials/{mid}",
        headers=_auth(tenant["token"]),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "READY"
    assert body["chunk_count"] > 0
    assert body["document"]["page_count"] == 2
    assert body["document"]["extraction_method"] == "TEXT"
    assert "storage_key" not in body


def test_document_and_chunk_pagination(client: TestClient, session, tenant) -> None:
    mid = _ready_material(client, tenant, session)
    base = f"/api/v1/projects/{tenant['project_id']}/materials/{mid}"
    doc = client.get(f"{base}/document", headers=_auth(tenant["token"]))
    assert doc.status_code == 200
    assert doc.json()["chunk_count"] > 0

    p1 = client.get(
        f"{base}/document/chunks?page=1&page_size=1", headers=_auth(tenant["token"])
    ).json()
    assert p1["total"] >= 2 and len(p1["items"]) == 1
    assert p1["items"][0]["chunk_index"] == 0
    assert p1["items"][0]["page_start"] == 1
    assert "embedding" not in p1["items"][0]
    p2 = client.get(
        f"{base}/document/chunks?page=2&page_size=1", headers=_auth(tenant["token"])
    ).json()
    assert p2["items"][0]["chunk_index"] == 1
    assert p2["items"][0]["page_start"] == 2


def test_document_not_ready_yet(client: TestClient, tenant) -> None:
    res = _upload(client, tenant["token"], tenant["project_id"])
    mid = res.json()["id"]
    base = f"/api/v1/projects/{tenant['project_id']}/materials/{mid}"
    assert client.get(f"{base}/document", headers=_auth(tenant["token"])).status_code == 404
    detail = client.get(base, headers=_auth(tenant["token"])).json()
    assert detail["status"] == "QUEUED" and detail["document"] is None


def test_material_list_counts_and_filters(client: TestClient, session, tenant) -> None:
    _ready_material(client, tenant, session, name="Done")
    _upload(client, tenant["token"], tenant["project_id"], title="Pending")
    listed = client.get(
        f"/api/v1/projects/{tenant['project_id']}/materials",
        headers=_auth(tenant["token"]),
    ).json()
    assert listed["total"] == 2
    by_name = {m["name"]: m for m in listed["items"]}
    assert by_name["Done"]["page_count"] == 2
    assert by_name["Done"]["chunk_count"] > 0
    assert by_name["Pending"]["page_count"] is None
    ready_only = client.get(
        f"/api/v1/projects/{tenant['project_id']}/materials?status=READY",
        headers=_auth(tenant["token"]),
    ).json()
    assert ready_only["total"] == 1


# ------------------------------------------------------------ reprocess / archive


def test_reprocess_rules(client: TestClient, session, tenant, monkeypatch) -> None:
    import app.api.routes.materials as routes

    monkeypatch.setattr(routes, "dispatch_processing", lambda _mid: True)
    mid = _ready_material(client, tenant, session)
    base = f"/api/v1/projects/{tenant['project_id']}/materials/{mid}"
    # READY cannot be reprocessed.
    assert client.post(f"{base}/reprocess", headers=_auth(tenant["token"])).status_code == 409
    # Force FAILED, then reprocess resets to QUEUED.
    mat = session.get(Material, mid)
    mat.status = MaterialStatus.FAILED
    mat.processing_error = "boom"
    session.commit()
    res = client.post(f"{base}/reprocess", headers=_auth(tenant["token"]))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "QUEUED"
    assert res.json()["processing_error"] is None


def test_archive_restore(client: TestClient, session, tenant) -> None:
    mid = _ready_material(client, tenant, session)
    base = f"/api/v1/projects/{tenant['project_id']}/materials/{mid}"
    assert client.delete(base, headers=_auth(tenant["token"])).status_code == 200
    listed = client.get(
        f"/api/v1/projects/{tenant['project_id']}/materials",
        headers=_auth(tenant["token"]),
    ).json()
    assert listed["total"] == 0
    assert client.get(base, headers=_auth(tenant["token"])).status_code == 404
    res = client.post(f"{base}/restore", headers=_auth(tenant["token"]))
    assert res.status_code == 200
    assert client.get(base, headers=_auth(tenant["token"])).status_code == 200


def test_cross_tenant_material_isolation(client: TestClient, session, tenant) -> None:
    mid = _ready_material(client, tenant, session)
    other = _register(client, "intruder@example.com")
    base = f"/api/v1/projects/{tenant['project_id']}/materials/{mid}"
    h = _auth(other)
    assert client.get(base, headers=h).status_code == 404
    assert client.get(f"{base}/document", headers=h).status_code == 404
    assert client.get(f"{base}/document/chunks", headers=h).status_code == 404
    assert client.post(f"{base}/reprocess", headers=h).status_code == 404
    assert client.delete(base, headers=h).status_code == 404
    assert (
        client.post(
            f"/api/v1/projects/{tenant['project_id']}/materials",
            headers=h,
            files={"file": ("n.pdf", PDF, "application/pdf")},
        ).status_code
        == 404
    )
