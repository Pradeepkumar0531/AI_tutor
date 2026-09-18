"""Platform administration: aggregate SQL over existing tables, no new logic.

Every method is admin-only at the route layer (``require_admin``); this
service assumes the caller is authorized. All lists are paginated and
server-filtered — never full-table loads. Responses carry no secrets:
no password hashes, tokens, keys, embeddings, or storage internals.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import check_database
from app.models.assessment import Assessment, QuizAttempt
from app.models.enums import (
    EventType,
    JobStatus,
    MaterialStatus,
    RecommendationStatus,
)
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.models.intelligence import Mastery, Recommendation
from app.models.learning import Project, Space
from app.models.materials import Material
from app.models.observability import AiUsage
from app.models.ops import Event, ProcessingJob
from app.models.tutor import Conversation, Message
from app.models.users import User
from app.services.base import BaseService

log = logging.getLogger("app.admin")

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def clamp_page(limit: int, offset: int) -> tuple[int, int]:
    return min(max(limit, 1), MAX_PAGE_SIZE), max(offset, 0)


class AdminService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    # ---------------------------------------------------------- overview
    def overview(self) -> dict:
        s = self.session
        counts: dict[str, object] = {
            "users": s.scalar(sa.select(sa.func.count()).select_from(User)),
            "admins": s.scalar(
                sa.select(sa.func.count()).select_from(User).where(User.role == "admin")
            ),
            "spaces": s.scalar(sa.select(sa.func.count()).select_from(Space)),
            "projects": s.scalar(sa.select(sa.func.count()).select_from(Project)),
            "materials": s.scalar(sa.select(sa.func.count()).select_from(Material)),
            "materials_ready": s.scalar(
                sa.select(sa.func.count())
                .select_from(Material)
                .where(Material.status == MaterialStatus.READY)
            ),
            "assessments": s.scalar(sa.select(sa.func.count()).select_from(Assessment)),
            "quiz_attempts": s.scalar(sa.select(sa.func.count()).select_from(QuizAttempt)),
            "tutor_conversations": s.scalar(sa.select(sa.func.count()).select_from(Conversation)),
            "tutor_messages": s.scalar(sa.select(sa.func.count()).select_from(Message)),
            "active_recommendations": s.scalar(
                sa.select(sa.func.count())
                .select_from(Recommendation)
                .where(Recommendation.status == RecommendationStatus.ACTIVE)
            ),
            "events": s.scalar(sa.select(sa.func.count()).select_from(Event)),
            "ai_calls": s.scalar(sa.select(sa.func.count()).select_from(AiUsage)),
            "evaluation_runs": s.scalar(sa.select(sa.func.count()).select_from(EvaluationRun)),
        }
        job_rows = self.session.execute(
            sa.select(ProcessingJob.status, sa.func.count()).group_by(ProcessingJob.status)
        ).all()
        counts["jobs"] = {str(status): total for status, total in job_rows}
        return counts

    # ---------------------------------------------------------- users
    def list_users(
        self, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[User], int]:
        limit, offset = clamp_page(limit, offset)
        stmt_count = sa.select(sa.func.count()).select_from(User)
        stmt_rows = sa.select(User).order_by(User.created_at.desc())
        if search and search.strip():
            # Bounded substring match on email only; pattern chars are escaped
            # so the filter cannot blow up into a full-table wildcard scan.
            needle = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt_count = stmt_count.where(User.email.ilike(f"%{needle}%", escape="\\"))
            stmt_rows = stmt_rows.where(User.email.ilike(f"%{needle}%", escape="\\"))
        total = self.session.scalar(stmt_count)
        rows = self.session.scalars(stmt_rows.limit(limit).offset(offset)).all()
        return list(rows), total or 0

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def user_journey(self, user_id: uuid.UUID) -> dict | None:
        """One user's learning journey: spaces/projects, counts, recent
        assessments, mastery snapshot, recommendations, AI usage, events."""
        user = self.get_user(user_id)
        if user is None:
            return None
        s = self.session
        project_ids = list(
            s.scalars(sa.select(Project.id).where(Project.owner_id == user_id)).all()
        )
        spaces = s.scalars(sa.select(Space).where(Space.owner_id == user_id).limit(100)).all()
        assessments = s.scalars(
            sa.select(Assessment)
            .where(Assessment.user_id == user_id)
            .order_by(Assessment.created_at.desc())
            .limit(20)
        ).all()
        recs = s.scalars(
            sa.select(Recommendation)
            .where(
                Recommendation.user_id == user_id,
                Recommendation.status == RecommendationStatus.ACTIVE,
            )
            .limit(20)
        ).all()
        mastery = (
            s.execute(
                sa.select(sa.func.count(), sa.func.avg(Mastery.score)).where(
                    Mastery.user_id == user_id
                )
            ).one()
            if project_ids
            else (0, None)
        )
        ai = s.execute(
            sa.select(sa.func.count(), sa.func.sum(AiUsage.estimated_cost_usd)).where(
                AiUsage.user_id == user_id
            )
        ).one()
        events = s.scalars(
            sa.select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.created_at.desc())
            .limit(30)
        ).all()
        return {
            "user": user,
            "project_ids": [str(p) for p in project_ids],
            "spaces": spaces,
            "assessments": assessments,
            "recommendations": recs,
            "mastery_concepts": mastery[0] or 0,
            "mastery_avg": round(float(mastery[1] or 0), 1),
            "ai_requests": ai[0] or 0,
            "ai_estimated_cost_usd": round(float(ai[1] or 0), 6),
            "recent_events": events,
        }

    # ---------------------------------------------------------- activity
    def activity(
        self,
        *,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
        space_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[Event], int]:
        limit, offset = clamp_page(limit, offset)
        q = sa.select(Event)
        count_q = sa.select(sa.func.count()).select_from(Event)
        filters = []
        if user_id is not None:
            # Scope to the user's own events OR events in their projects.
            owned_projects = sa.select(Project.id).where(Project.owner_id == user_id)
            filters.append(
                sa.or_(
                    Event.user_id == user_id,
                    Event.project_id.in_(owned_projects),
                )
            )
        if space_id is not None:
            in_space = sa.select(Project.id).where(Project.space_id == space_id)
            filters.append(
                sa.or_(
                    Event.project_id.in_(in_space),
                    # Space-level events (e.g. SPACE_CREATED) carry no
                    # project_id — match them by entity reference instead.
                    sa.and_(
                        Event.entity_type == "space",
                        Event.entity_id == space_id,
                    ),
                )
            )
        if project_id is not None:
            filters.append(Event.project_id == project_id)
        if event_type is not None:
            try:
                filters.append(Event.event_type == EventType(event_type))
            except ValueError:
                return [], 0
        if since is not None:
            filters.append(Event.created_at >= since)
        if until is not None:
            filters.append(Event.created_at <= until)
        for f in filters:
            q = q.where(f)
            count_q = count_q.where(f)
        total = self.session.scalar(count_q) or 0
        rows = self.session.scalars(
            q.order_by(Event.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    # ---------------------------------------------------------- jobs
    def jobs(
        self, *, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[ProcessingJob], int]:
        limit, offset = clamp_page(limit, offset)
        q = sa.select(ProcessingJob)
        count_q = sa.select(sa.func.count()).select_from(ProcessingJob)
        if status is not None:
            try:
                st = JobStatus(status)
            except ValueError:
                return [], 0
            q = q.where(ProcessingJob.status == st)
            count_q = count_q.where(ProcessingJob.status == st)
        total = self.session.scalar(count_q) or 0
        rows = self.session.scalars(
            q.order_by(ProcessingJob.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    # ---------------------------------------------------------- health
    def health(self) -> dict:
        settings = get_settings()
        db = check_database()
        ai = {
            "groq_configured": bool(settings.groq_api_key),
            "google_configured": bool(settings.google_api_key),
            "fake_ai": bool(settings.test_fake_ai),
        }
        storage = {
            "backend": settings.storage_backend,
            "neon_configured": bool(
                settings.neon_storage_endpoint
                and settings.neon_storage_access_key_id
                and settings.neon_storage_secret_access_key
                and settings.neon_storage_bucket_name
            ),
        }
        queue = {
            "broker_configured": bool(settings.celery_broker_url or settings.upstash_redis_url),
        }
        statuses = [
            "healthy" if db.get("reachable") else "degraded",
            "healthy" if (ai["groq_configured"] or ai["fake_ai"]) else "degraded",
            "healthy"
            if (storage["backend"] == "local" or storage["neon_configured"])
            else "degraded",
        ]
        overall = "healthy" if all(s == "healthy" for s in statuses) else "degraded"
        return {
            "overall": overall,
            "api": "healthy",
            "database": "healthy" if db.get("reachable") else "degraded",
            "database_configured": bool(db.get("configured")),
            "ai": ai,
            "storage": storage,
            "queue": queue,
        }

    # ---------------------------------------------------------- evaluations
    def evaluation_runs(self, *, limit: int, offset: int) -> tuple[list[EvaluationRun], int]:
        limit, offset = clamp_page(limit, offset)
        total = self.session.scalar(sa.select(sa.func.count()).select_from(EvaluationRun))
        rows = self.session.scalars(
            sa.select(EvaluationRun)
            .order_by(EvaluationRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total or 0

    def evaluation_summary(self) -> dict | None:
        run = self.session.scalars(
            sa.select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(1)
        ).one_or_none()
        if run is None:
            return None
        by_cat = self.session.execute(
            sa.select(
                EvaluationResult.category,
                sa.func.count(),
                sa.func.sum(sa.case((EvaluationResult.passed.is_(True), 1), else_=0)),
            )
            .where(EvaluationResult.run_id == run.id)
            .group_by(EvaluationResult.category)
        ).all()
        failures = self.session.scalars(
            sa.select(EvaluationResult)
            .where(
                EvaluationResult.run_id == run.id,
                EvaluationResult.passed.is_(False),
            )
            .limit(20)
        ).all()
        return {
            "run_id": str(run.id),
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "total": run.total_cases,
            "passed": run.passed,
            "failed": run.failed,
            "by_category": [{"category": c, "total": t, "passed": p} for c, t, p in by_cat],
            "recent_failures": [
                {"case_id": f.case_id, "category": f.category, "reason": f.reason[:300]}
                for f in failures
            ],
        }
