"""PDF embedded images: extraction, filtering, provenance, storage,
idempotency, authorization, knowledge integration, RAG compatibility."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.documents.images import (
    build_image_storage_key,
    extract_embedded_images,
    filter_images,
)
from app.documents.pipeline import PipelineConfig, process_pdf
from app.jobs.document_tasks import execute_material_processing
from app.models.enums import MaterialStatus
from app.models.materials import DocumentImage
from app.storage import LocalStorage, ObjectNotFoundError, StorageError, StorageService
from tests.conftest import make_project, make_user
from tests.pdf_fixtures import make_image_pdf, make_text_pdf

TEXTS = [
    "Photosynthesis converts sunlight into chemical energy in plants.",
    "Mitochondria release stored energy as ATP in animal cells.",
]


def _large_pdf() -> bytes:
    return make_image_pdf(
        [
            {"text": TEXTS[0], "images": [(300, 200, 7), (250, 180, 8)]},
            {"text": TEXTS[1], "images": [(300, 200, 7)]},
        ]
    )


def _service_storage(tmp_path) -> StorageService:
    return StorageService(LocalStorage(root=str(tmp_path / "storage")), provider="local")


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Route service storage reads to the test tmp dir (same pattern as
    test_materials.py)."""
    import app.services.material_service as svc

    backend = LocalStorage(root=str(tmp_path / "storage"))
    monkeypatch.setattr(
        svc, "get_storage_service", lambda: StorageService(backend, provider="local")
    )
    return backend


def _material(session: Session, storage: StorageService, data: bytes):
    from app.repositories.materials import MaterialRepository, ProcessingJobRepository

    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(
        project_id=project.id,
        name="Doc",
        original_filename="d.pdf",
        mime_type="application/pdf",
        file_size=len(data),
    )
    session.flush()
    key = f"projects/{project.id.hex}/materials/{mat.id.hex}/original.pdf"
    storage.put(key, data, "application/pdf")
    mat.storage_key = key
    ProcessingJobRepository(session).enqueue(
        job_type="document.process",
        project_id=project.id,
        material_id=mat.id,
        idempotency_key=f"material:{mat.id}:process",
        payload={"material_id": str(mat.id)},
    )
    session.commit()
    return owner, project, mat


def _run(session, storage, mat, **kwargs):
    from tests.test_processing import NullOcrProvider

    return execute_material_processing(
        mat.id,
        session=session,
        settings=get_settings(),
        storage=storage,
        ocr_provider_factory=kwargs.get("ocr_factory", NullOcrProvider),
    )


# ------------------------------------------------------------- extraction


def test_extract_single_and_multi_page_images() -> None:
    raw = extract_embedded_images(_large_pdf(), max_pages=500)
    by_page: dict[int, list] = {}
    for image in raw:
        by_page.setdefault(image.page_number, []).append(image)
    assert sorted(by_page) == [1, 2]
    assert [i.image_index for i in by_page[1]] == [0, 1]
    assert [i.image_index for i in by_page[2]] == [0]
    first = by_page[1][0]
    assert (first.width, first.height) == (300, 200)
    assert first.mime_type == "image/png"
    assert first.ext == "png"
    assert first.size_bytes > 2048
    assert len(first.sha256) == 64
    assert first.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_duplicate_bytes_share_hash() -> None:
    raw = extract_embedded_images(_large_pdf(), max_pages=500)
    hashes = [i.sha256 for i in raw]
    # Same seed/size on both pages: identical bytes, distinct placements.
    assert len(set(hashes)) == 2
    assert hashes[0] == hashes[2]
    assert raw[0].page_number == 1 and raw[2].page_number == 2


def test_extract_ignores_text_only_pdf() -> None:
    raw = extract_embedded_images(make_text_pdf(TEXTS), max_pages=500)
    assert raw == []


def test_extract_skips_alpha_masks() -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 500, 150), "Text with a transparent image.")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.Rect(0, 0, 300, 200), 1)
    assert pix.alpha
    pix.set_alpha(b"\x80" * (300 * 200))
    page.insert_image(pymupdf.Rect(72, 170, 372, 370), pixmap=pix, alpha=0)
    raw = extract_embedded_images(bytes(doc.tobytes()), max_pages=500)
    # The color image is kept; its alpha mask is not a separate image.
    assert len(raw) == 1
    assert raw[0].width == 300


# ------------------------------------------------------------- filtering


def test_filter_drops_tiny_images() -> None:
    import pymupdf

    from tests.pdf_fixtures import make_noise_pixmap

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 500, 150), "Icons and bullets everywhere.")
    page.insert_image(pymupdf.Rect(72, 170, 80, 178), pixmap=make_noise_pixmap(8, 8, seed=1))
    page.insert_image(pymupdf.Rect(72, 200, 372, 400), pixmap=make_noise_pixmap(300, 200, seed=2))
    raw = extract_embedded_images(bytes(doc.tobytes()), max_pages=500)
    assert len(raw) == 2
    kept, stats = filter_images(
        raw, min_width=100, min_height=100, min_bytes=2048, max_per_page=10, max_per_doc=50
    )
    assert len(kept) == 1
    assert kept[0].width == 300
    assert stats == {"extracted": 2, "kept": 1, "filtered": 1}


def test_filter_caps_and_disable_flag() -> None:
    raw = extract_embedded_images(_large_pdf(), max_pages=500)
    kept, _ = filter_images(
        raw, min_width=1, min_height=1, min_bytes=1, max_per_page=1, max_per_doc=50
    )
    assert [i.image_index for i in kept] == [0, 0]  # first per page, deterministic
    kept, _ = filter_images(
        raw, min_width=1, min_height=1, min_bytes=1, max_per_page=10, max_per_doc=2
    )
    assert len(kept) == 2
    res = process_pdf(
        _large_pdf(),
        PipelineConfig(image_extraction_enabled=False),
        None,
    )
    assert res.images == []
    assert res.image_stats["kept"] == 0


def test_oversized_image_is_kept_with_dimensions() -> None:
    import pymupdf

    from tests.pdf_fixtures import make_noise_pixmap

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 500, 150), "A full-page scan figure.")
    page.insert_image(pymupdf.Rect(0, 0, 1200, 1600), pixmap=make_noise_pixmap(300, 400, seed=9))
    raw = extract_embedded_images(bytes(doc.tobytes()), max_pages=500)
    assert len(raw) == 1
    assert raw[0].width == 300 and raw[0].height == 400
    kept, _ = filter_images(
        raw, min_width=100, min_height=100, min_bytes=1, max_per_page=10, max_per_doc=50
    )
    assert len(kept) == 1  # no upper size cap: large figures are content


# ------------------------------------------------------------- pipeline


def test_pipeline_result_carries_images_and_counts() -> None:
    from tests.test_processing import NullOcrProvider

    res = process_pdf(_large_pdf(), PipelineConfig(), NullOcrProvider())
    assert res.page_count == 2
    assert res.chunk_count >= 2  # text path unchanged
    assert len(res.images) == 3  # duplicate placement kept per page (provenance)
    assert res.image_stats == {"extracted": 3, "kept": 3, "filtered": 0}
    assert res.doc_metadata["images_kept"] == 3
    assert all(i.page_number in (1, 2) for i in res.images)


def test_pipeline_text_only_unchanged() -> None:
    from tests.test_processing import NullOcrProvider

    res = process_pdf(make_text_pdf(TEXTS), PipelineConfig(), NullOcrProvider())
    assert res.images == []
    assert res.image_stats == {"extracted": 0, "kept": 0, "filtered": 0}


# ------------------------------------------------------------- storage keys


def test_storage_key_format_and_containment() -> None:
    import uuid

    pid, mid = uuid.uuid4(), uuid.uuid4()
    key = build_image_storage_key(project_id=pid, material_id=mid, sha256="ab" * 32, ext="png")
    assert key == f"projects/{pid.hex}/materials/{mid.hex}/images/{'ab' * 32}.png"
    assert len(key) <= 512
    store = StorageService(LocalStorage(root="/tmp"), provider="local")
    store._backend._path(key)  # containment check passes
    with pytest.raises(StorageError):
        store._backend._path("../../escape")
    with pytest.raises(StorageError):
        store._backend._path("/absolute")


def test_local_storage_roundtrip_and_missing(tmp_path) -> None:
    store = _service_storage(tmp_path)
    store.put("a/b.png", b"bytes", "image/png")
    assert store.get("a/b.png") == b"bytes"
    assert store.exists("a/b.png") is True
    assert store.exists("a/nope.png") is False
    with pytest.raises(ObjectNotFoundError):
        store.get("a/nope.png")


# ------------------------------------------------------------- job persist


def test_job_persists_images_idempotently(session: Session, tmp_path) -> None:
    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, _large_pdf())
    out = _run(session, storage, mat)
    assert out["status"] == "READY"
    assert out["images"] == 2  # unique binaries stored

    import sqlalchemy as sa

    rows = session.scalars(
        sa.select(DocumentImage).order_by(DocumentImage.page_number, DocumentImage.image_index)
    ).all()
    assert [(r.page_number, r.image_index) for r in rows] == [(1, 0), (1, 1), (2, 0)]
    first = rows[0]
    assert first.project_id == project.id
    assert first.material_id == mat.id
    assert first.document_id is not None
    assert first.width == 300 and first.mime_type == "image/png"
    assert len(first.sha256) == 64
    # Duplicate binary shares one storage object across both page rows.
    assert rows[0].storage_key == rows[2].storage_key
    assert rows[0].storage_key != rows[1].storage_key
    assert storage.get(rows[0].storage_key) == storage.get(rows[2].storage_key)
    assert mat.status == MaterialStatus.READY

    # Re-running a successful material: no duplicates, same rows.
    again = _run(session, storage, mat)
    assert again["status"] == "already-done"
    import sqlalchemy as sa

    assert session.scalar(sa.select(sa.func.count(DocumentImage.id))) == 3


def test_retry_after_storage_failure_leaves_no_orphans(session: Session, tmp_path) -> None:
    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, _large_pdf())

    real_put = storage.put
    calls = {"n": 0}

    def flaky_put(key: str, data: bytes, content_type: str = "image/png") -> str:
        calls["n"] += 1
        if calls["n"] == 1 and key.endswith(".png") and "images/" in key:
            raise StorageError("transient outage")
        return real_put(key, data, content_type)

    storage.put = flaky_put  # type: ignore[method-assign]
    from app.jobs.retry import NeedsRetry

    with pytest.raises(NeedsRetry):
        _run(session, storage, mat)
    storage.put = real_put  # type: ignore[method-assign]
    out = _run(session, storage, mat)
    assert out["status"] == "READY"

    import sqlalchemy as sa

    referenced = {r.storage_key for r in session.scalars(sa.select(DocumentImage))}
    on_disk = {
        str(p.relative_to(tmp_path / "storage"))
        for p in (tmp_path / "storage").rglob("*")
        if p.is_file()
    }
    mat_key = mat.storage_key
    assert mat_key is not None and mat_key in on_disk
    assert set(referenced) <= on_disk
    assert len(on_disk - set(referenced) - {mat_key}) == 0


def test_rebuild_with_new_bytes_cleans_superseded_objects(session: Session, tmp_path) -> None:
    import sqlalchemy as sa

    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, _large_pdf())
    assert _run(session, storage, mat)["status"] == "READY"
    old_keys = {r.storage_key for r in session.scalars(sa.select(DocumentImage))}
    assert len(old_keys) == 2  # seeds 7/8 differ; seed-7 rows share one key

    # New PDF revision: single distinct image.
    from tests.pdf_fixtures import make_image_pdf

    v2 = make_image_pdf([{"text": TEXTS[0], "images": [(300, 200, 21)]}])
    assert storage.get(mat.storage_key) is not None
    storage.put(mat.storage_key, v2, "application/pdf")
    mat.status = MaterialStatus.QUEUED
    session.commit()
    # Reset the succeeded job so the worker claim proceeds (retry semantics).
    from app.models.ops import ProcessingJob

    job = session.query(ProcessingJob).filter_by(material_id=mat.id).one()
    job.status = "QUEUED"
    session.commit()
    assert _run(session, storage, mat)["status"] == "READY"
    rows = session.scalars(sa.select(DocumentImage)).all()
    assert len(rows) == 1
    assert rows[0].page_number == 1
    for key in old_keys - {rows[0].storage_key}:
        assert storage.exists(key) is False
    assert storage.exists(rows[0].storage_key) is True


# ------------------------------------------------------------- services + API


def _ready_material(session, tmp_path):
    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, _large_pdf())
    assert _run(session, storage, mat)["status"] == "READY"
    return storage, owner, project, mat


def test_service_list_get_bytes(session: Session, tmp_path, isolated_storage) -> None:
    from app.services.material_service import MaterialService

    storage, owner, project, mat = _ready_material(session, tmp_path)
    svc = MaterialService(session)
    items, total = svc.list_document_images(
        user_id=owner.id, project_id=project.id, material_id=mat.id
    )
    assert total == 3
    assert [(i.page_number, i.image_index) for i in items] == [(1, 0), (1, 1), (2, 0)]
    first = svc.get_document_image(
        user_id=owner.id, project_id=project.id, material_id=mat.id, image_id=items[0].id
    )
    assert first.id == items[0].id
    data, mime = svc.get_image_bytes(
        user_id=owner.id, project_id=project.id, material_id=mat.id, image_id=items[0].id
    )
    assert mime == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data == storage.get(items[0].storage_key)


def test_missing_binary_is_404_not_key_leak(session: Session, tmp_path, isolated_storage) -> None:
    from app.services.material_service import MaterialService

    storage, owner, project, mat = _ready_material(session, tmp_path)
    svc = MaterialService(session)
    items, _ = svc.list_document_images(user_id=owner.id, project_id=project.id, material_id=mat.id)
    storage.delete(items[0].storage_key)
    with pytest.raises(NotFoundError):
        svc.get_image_bytes(
            user_id=owner.id, project_id=project.id, material_id=mat.id, image_id=items[0].id
        )


def test_isolation_matrix(session: Session, tmp_path, isolated_storage) -> None:
    from app.services.material_service import MaterialService

    storage, owner, project, mat = _ready_material(session, tmp_path)
    svc = MaterialService(session)
    items, _ = svc.list_document_images(user_id=owner.id, project_id=project.id, material_id=mat.id)
    image_id = items[0].id
    stranger = make_user(session, email="stranger@example.com")
    other_project = make_project(session, stranger)
    other_mat_owner, other_project2, other_mat = _material(session, storage, _large_pdf())

    # A -> A allowed is covered above; everything else is 404.
    with pytest.raises(NotFoundError):
        svc.list_document_images(user_id=stranger.id, project_id=project.id, material_id=mat.id)
    with pytest.raises(NotFoundError):
        svc.get_document_image(
            user_id=stranger.id, project_id=project.id, material_id=mat.id, image_id=image_id
        )
    with pytest.raises(NotFoundError):
        svc.get_image_bytes(
            user_id=stranger.id, project_id=project.id, material_id=mat.id, image_id=image_id
        )
    # Cross-material: A's image requested under B's material.
    with pytest.raises(NotFoundError):
        svc.get_document_image(
            user_id=owner.id,
            project_id=other_project2.id,
            material_id=other_mat.id,
            image_id=image_id,
        )
    # Cross-project: A's image under a foreign project id.
    with pytest.raises(NotFoundError):
        svc.get_document_image(
            user_id=stranger.id,
            project_id=other_project.id,
            material_id=mat.id,
            image_id=image_id,
        )


def test_material_detail_and_knowledge_counts(session: Session, tmp_path) -> None:
    from app.services.knowledge_service import KnowledgeService
    from app.services.material_service import MaterialService

    _, owner, project, mat = _ready_material(session, tmp_path)
    _, _, chunk_count, image_count = MaterialService(session).get_material_detail(
        user_id=owner.id, project_id=project.id, material_id=mat.id
    )
    assert chunk_count >= 2
    assert image_count == 3
    summary = KnowledgeService(session).material_knowledge(
        user_id=owner.id, project_id=project.id, material_id=mat.id
    )
    assert summary["image_count"] == 3
    assert summary["images_by_page"] == {1: 2, 2: 1}


def test_routes_learner_safe_and_content(session: Session, tmp_path, isolated_storage) -> None:
    import json

    from fastapi.testclient import TestClient

    from app.auth.dependencies import get_current_user
    from app.db.session import get_db
    from app.main import create_app

    _, owner, project, mat = _ready_material(session, tmp_path)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: session

    async def _owner():
        return owner

    app.dependency_overrides[get_current_user] = _owner
    try:
        client = TestClient(app)
        listed = client.get(f"/api/v1/projects/{project.id}/materials/{mat.id}/images")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] == 3
        first = body["items"][0]
        assert first["page_number"] == 1
        assert "storage_key" not in json.dumps(first)
        assert "sha256" not in json.dumps(first)
        assert set(first) >= {
            "id",
            "document_id",
            "page_number",
            "image_index",
            "width",
            "height",
            "mime_type",
            "file_size",
        }
        detail = client.get(
            f"/api/v1/projects/{project.id}/materials/{mat.id}/images/{first['id']}"
        )
        assert detail.status_code == 200
        content = client.get(
            f"/api/v1/projects/{project.id}/materials/{mat.id}/images/{first['id']}/content"
        )
        assert content.status_code == 200
        assert content.headers["content-type"] == "image/png"
        assert content.content[:8] == b"\x89PNG\r\n\x1a\n"
        material = client.get(f"/api/v1/projects/{project.id}/materials/{mat.id}")
        assert material.json()["image_count"] == 3
        assert material.json()["document"]["image_count"] == 3
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------- RAG + regression


def test_rag_image_references_are_metadata_only() -> None:
    from app.rag.retrieval import format_image_references

    out = format_image_references(
        [
            {
                "document_id": "d1",
                "page_number": 17,
                "image_index": 2,
                "mime_type": "image/png",
                "width": 1200,
                "height": 800,
            }
        ]
    )
    assert "[IMAGE]" in out and "[/IMAGE]" in out
    assert "Page: 17" in out and "Image: 2" in out
    assert "1200x800" in out
    assert "photosynthesis" not in out.lower()


def test_text_only_material_has_no_images(session: Session, tmp_path) -> None:
    import sqlalchemy as sa

    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, make_text_pdf(TEXTS))
    out = _run(session, storage, mat)
    assert out["status"] == "READY"
    assert out.get("images", 0) == 0
    assert session.scalar(sa.select(sa.func.count(DocumentImage.id))) == 0


def test_cross_project_link_rejected_by_database(session: Session, tmp_path) -> None:
    import sqlalchemy as sa
    import sqlalchemy.exc

    from app.models.materials import Document

    storage = _service_storage(tmp_path)
    owner, project, mat = _material(session, storage, _large_pdf())
    assert _run(session, storage, mat)["status"] == "READY"
    other = make_project(session, make_user(session, email="other@example.com"))
    document = session.scalars(sa.select(Document)).first()
    assert document is not None
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        session.add(
            DocumentImage(
                document_id=document.id,
                material_id=mat.id,
                project_id=other.id,  # lies: document lives in `project`
                page_number=1,
                image_index=9,
                width=100,
                height=100,
                mime_type="image/png",
                file_size=10,
                storage_key="k",
                sha256="s",
            )
        )
        session.flush()
    session.rollback()
