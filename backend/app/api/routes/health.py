"""Liveness + readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict:
    return {"status": "ok", "service": "ai-learning-companion"}


@router.get("/health/ready")
def readiness() -> dict:
    db = check_database()
    ready = (not db.get("configured")) or bool(db.get("reachable"))
    # Liveness never fails here; readiness reports degraded instead of 500 so local
    # dev without Neon/Upstash stays usable. Orchestrators can key off `ready`.
    return {"ready": ready, "database": db}
