#!/usr/bin/env python3
"""Production-style smoke test: full learning loop without a server/worker.

Uses FastAPI TestClient (in-process uvicorn stack), a throwaway SQLite file,
local storage, and TEST_FAKE_AI providers — no network, no credentials.
Exercises: health, readiness, register, login, /me, space, project, material
upload, document processing (real worker function), knowledge processing
(real worker function), RAG search, tutor send, quiz create/answer/complete,
mastery, growth, recommendations, dashboard, events, logout.

Covers §55 without claiming live-provider verification.
Usage:  cd backend && TEST_FAKE_AI=true .venv/bin/python ../scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["TEST_FAKE_AI"] = "true"
# Ignore the developer's backend/.env entirely (pydantic-settings reads it via
# dotenv even when os.environ is scrubbed) — hermetic throwaway infra only.
os.environ.setdefault("APP_ENV_FILE", os.devnull)
tmp = tempfile.mkdtemp(prefix="smoke-")
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/smoke.db"
os.environ["LOCAL_STORAGE_DIR"] = f"{tmp}/storage"
# Hermetic by design (no network, no credentials): drop ambient infrastructure
# secrets (e.g. a developer's backend/.env with a real rediss:// result
# backend, which fails eagerly at dispatch time) before the app boots.
for _var in (
    "CORS_ORIGINS",
    "JWT_SECRET_KEY",
    "SECRET_KEY",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "UPSTASH_REDIS_URL",
    "UPSTASH_REDIS_TOKEN",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY_FILESYSTEM_ROOT",
    "STORAGE_BACKEND",
    "NEON_STORAGE_ENDPOINT",
    "NEON_STORAGE_REGION",
    "NEON_STORAGE_ACCESS_KEY_ID",
    "NEON_STORAGE_SECRET_ACCESS_KEY",
    "NEON_STORAGE_BUCKET_NAME",
):
    os.environ.pop(_var, None)
if "prod" in os.environ.get("DATABASE_URL", ""):
    raise SystemExit("Refusing to smoke-test what looks like a production database.")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

STEPS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    STEPS.append(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
    if not cond:
        raise SystemExit(f"SMOKE FAILED at: {name} {detail}")


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng)()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    client = TestClient(app)

    r = client.get("/api/v1/health")
    check("health", r.status_code == 200, r.text[:80])
    r = client.get("/api/v1/health/ready")
    check("readiness", r.status_code == 200, r.text[:120])

    email = "smoke@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SmokePass123", "display_name": "Smoke"},
    )
    check("register", r.status_code == 201, r.text[:80])
    token = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SmokePass123"}
    )
    check("login", r.status_code == 200)
    r = client.get("/api/v1/auth/me", headers=auth)
    check("me", r.status_code == 200 and r.json()["email"] == email)

    r = client.post("/api/v1/spaces", json={"name": "S"}, headers=auth)
    check("space", r.status_code == 201)
    space_id = r.json()["id"]
    r = client.post(
        "/api/v1/projects", json={"space_id": space_id, "name": "P"}, headers=auth
    )
    check("project", r.status_code == 201)
    project_id = r.json()["id"]

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "tests"))
    from pdf_fixtures import make_text_pdf

    # Chunk text carries a material keyword so the identical string both
    # retrieves (exact hash-similarity hit) and routes PROJECT_GROUNDED.
    pdf = make_text_pdf(
        ["This PDF explains photosynthesis and sunlight energy.",
         "This PDF explains mitochondria and ATP energy release."]
    )
    r = client.post(
        f"/api/v1/projects/{project_id}/materials",
        files={"file": ("smoke.pdf", pdf, "application/pdf")},
        headers=auth,
    )
    check("upload", r.status_code == 201, r.text[:80])
    material_id = r.json()["id"]

    # Worker steps executed in-process (same functions Celery would run).
    import uuid

    from app.core.config import get_settings
    from app.jobs.document_tasks import execute_material_processing
    from app.jobs.knowledge_tasks import execute_knowledge_processing
    from app.storage import get_storage_service

    settings = get_settings()
    out = execute_material_processing(
        uuid.UUID(material_id), session=session, settings=settings,
        storage=get_storage_service(),
        ocr_provider_factory=lambda: None,
    )
    check("document-processing", out.get("status") == "READY", str(out)[:100])
    session.commit()
    out = execute_knowledge_processing(
        uuid.UUID(material_id), session=session, settings=settings
    )
    check("knowledge-processing", "embedded" in str(out), str(out)[:100])
    session.commit()

    r = client.post(
        f"/api/v1/projects/{project_id}/knowledge/search",
        json={"query": "This PDF explains photosynthesis and sunlight energy."},
        headers=auth,
    )
    check(
        "rag-search",
        r.status_code == 200 and not r.json()["insufficient_evidence"],
        r.text[:100],
    )

    r = client.post(
        f"/api/v1/projects/{project_id}/conversations", json={}, headers=auth
    )
    check("conversation", r.status_code == 201)
    conv_id = r.json()["id"]
    r = client.post(
        f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages",
        json={"content": "This PDF explains photosynthesis and sunlight energy."},
        headers=auth,
    )
    check("tutor", r.status_code == 200 and r.json()["grounded"] is True, r.text[:100])

    r = client.post(
        f"/api/v1/projects/{project_id}/quizzes",
        json={"question_count": 2, "question_types": ["MCQ"]},
        headers=auth,
    )
    check("quiz-create", r.status_code == 201, r.text[:100])
    quiz_id = r.json()["quiz"]["id"]
    r = client.post(
        f"/api/v1/projects/{project_id}/quizzes/{quiz_id}/attempts", headers=auth
    )
    check("attempt", r.status_code == 201)
    attempt_id = r.json()["attempt"]["id"]
    for question in r.json()["questions"]:
        options = question["options"]
        if question["type"] == "OPEN_ENDED":
            answer_text = options[0]["text"] if options else "Mitochondria release energy."
            payload = {"question_id": question["question_id"], "answer": answer_text}
        else:
            payload = {"question_id": question["question_id"], "answer": options[0]["id"]}
        answer = client.post(
            f"/api/v1/projects/{project_id}/attempts/{attempt_id}/answers",
            json=payload,
            headers=auth,
        )
        check(f"answer-{question['question_id'][:8]}", answer.status_code == 200, answer.text[:80])
    r = client.post(
        f"/api/v1/projects/{project_id}/attempts/{attempt_id}/complete", headers=auth
    )
    check("complete", r.status_code == 200, r.text[:100])

    r = client.get(f"/api/v1/projects/{project_id}/mastery", headers=auth)
    check("mastery", r.status_code == 200 and r.json()["total"] >= 1, r.text[:100])
    r = client.get(f"/api/v1/projects/{project_id}/growth", headers=auth)
    check("growth", r.status_code == 200 and r.json()["has_evidence"] is True, r.text[:100])
    r = client.get(f"/api/v1/projects/{project_id}/recommendations", headers=auth)
    check("recommendations", r.status_code == 200)
    r = client.get(f"/api/v1/projects/{project_id}/analytics/dashboard", headers=auth)
    check(
        "dashboard",
        r.status_code == 200 and r.json()["has_learning_evidence"] is True,
        r.text[:100],
    )
    r = client.get(f"/api/v1/projects/{project_id}/events?page_size=5", headers=auth)
    check("events", r.status_code == 200 and r.json()["total"] >= 1)

    r = client.post("/api/v1/auth/logout", headers=auth)
    check("logout", r.status_code in (200, 204))

    print("\n".join(STEPS))
    print(f"\nSMOKE OK ({len(STEPS)} checks), tmpdir={tmp}")


if __name__ == "__main__":
    main()
