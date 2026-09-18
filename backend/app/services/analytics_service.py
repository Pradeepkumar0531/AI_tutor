"""Read-only learning analytics (Prompt 11): aggregates over authoritative
state + the event activity stream. No new algorithms, no writes, no mastery/
growth/recommendation/assessment recomputation — those services own their
numbers; this layer only reads them.

Metric sources (auditable, documented):
- materials/ready/failed ... Material rows (GROUP BY, non-archived)
- documents/pages ......... Document rows (SUM page_count, non-archived)
- chunks .................. DocumentChunk rows (COUNT)
- images .................. DocumentImage rows (COUNT)
- concepts ................ Concept rows (COUNT)
- assessments/questions ... Assessment rows' concept_results (bounded scan)
- overall/confidence/status  GrowthService.project_growth (single source)
- recommendations ......... Recommendation rows by status (GROUP BY)
- tutor convos/messages .... Conversation/Message rows (COUNT + JOIN)
- activity/timeline ....... Event rows (SQL-filtered feed + GROUP BY day)

UTC everywhere: grouping uses the stored UTC calendar date on both dialects;
the frontend converts for display only.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.assessment import Assessment
from app.models.enums import EventType, GrowthStatus
from app.models.learning import Project
from app.models.mixins import utcnow
from app.models.users import User
from app.repositories.assessments import AssessmentRepository
from app.repositories.intelligence import EventRepository, RecommendationRepository
from app.repositories.knowledge import ConceptRepository, ConversationRepository, MessageRepository
from app.repositories.materials import (
    ChunkRepository,
    DocumentImageRepository,
    DocumentRepository,
    MaterialRepository,
)
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService
from app.services.event_service import sanitize_payload

log = logging.getLogger("app.services.analytics")

RANGE_DAYS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}
VALID_RANGES = tuple(RANGE_DAYS)

# Timeline shows milestones, not pipeline internals or per-question noise.
TIMELINE_TYPES = (
    EventType.PROJECT_CREATED,
    EventType.MATERIAL_UPLOADED,
    EventType.MATERIAL_READY,
    EventType.MATERIAL_FAILED,
    EventType.CONVERSATION_CREATED,
    EventType.TUTOR_MESSAGE,
    EventType.QUIZ_CREATED,
    EventType.QUIZ_STARTED,
    EventType.ASSESSMENT_COMPLETED,
    EventType.MASTERY_UPDATED,
    EventType.RECOMMENDATION_GENERATED,
)


@dataclass
class DashboardSummary:
    project_id: uuid.UUID
    project_name: str
    materials_count: int = 0
    materials_ready: int = 0
    materials_failed: int = 0
    documents_count: int = 0
    pages_count: int = 0
    chunks_count: int = 0
    images_count: int = 0
    concepts_count: int = 0
    assessment_count: int = 0
    questions_answered: int = 0
    questions_correct: int = 0
    questions_partial: int = 0
    questions_incorrect: int = 0
    average_assessment_score: float | None = None
    overall_mastery: float | None = None
    mastery_confidence: float | None = None
    growth_status: GrowthStatus | None = None
    active_recommendations: int = 0
    tutor_conversations: int = 0
    tutor_messages: int = 0
    last_activity_at: datetime | None = None
    has_learning_evidence: bool = False


@dataclass
class ActivityItem:
    id: uuid.UUID
    event_type: EventType
    created_at: datetime
    resource_id: uuid.UUID | None
    metadata: dict | None
    summary: str


@dataclass
class ActivityDay:
    date: str  # YYYY-MM-DD in UTC
    count: int


class AnalyticsService(BaseService):
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.projects = ProjectRepository(session)
        self.events = EventRepository(session)
        self.materials = MaterialRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.images = DocumentImageRepository(session)
        self.concepts = ConceptRepository(session)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.assessments = AssessmentRepository(session)
        self.recommendations = RecommendationRepository(session)

    # ------------------------------------------------------------ dashboard

    def dashboard_summary(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> DashboardSummary:
        """One aggregated read (~15 small indexed statements, no bodies
        loaded). Timed + logged for slow-query diagnosis."""
        started = time.perf_counter()
        project = self._owned_project(user_id, project_id)

        content = self.materials.content_summary(project.id)
        documents, pages = self.documents.project_stats(project.id)
        chunks = self.chunks.project_total(project.id)
        images = self.images.project_total(project.id)
        concepts = self.concepts.count_for_project(project.id)

        assessments = self.assessments.recent_for_project_user(project.id, user_id, limit=200)
        answered = correct = partial = incorrect = 0
        scores: list[float] = []
        for assessment in assessments:
            if assessment.score is not None:
                scores.append(assessment.score / 100)
            for entry in assessment.concept_results or []:
                try:
                    answered += int(entry.get("questions_seen", 0) or 0)
                    correct += int(entry.get("correct_count", 0) or 0)
                    partial += int(entry.get("partial_count", 0) or 0)
                    incorrect += int(entry.get("incorrect_count", 0) or 0)
                except (ValueError, TypeError, AttributeError):
                    continue

        from app.services.growth_service import GrowthService

        growth = GrowthService(self.session, settings=self.settings).project_growth(
            user_id=user_id, project_id=project.id
        )
        rec_counts = self.recommendations.counts_by_status(project.id, user_id)
        from app.models.enums import RecommendationStatus

        convos = self.conversations.count_for_project(project.id, user_id)
        messages = self.messages.count_for_project(project.id, user_id)
        latest = self.events.feed(project.id, user_id, page=1, page_size=1)[0]
        last_activity = latest[0].created_at if latest else None

        has_evidence = bool(assessments) or messages > 0
        summary = DashboardSummary(
            project_id=project.id,
            project_name=project.name,
            materials_count=content["materials"],
            materials_ready=content["ready"],
            materials_failed=content["failed"],
            documents_count=documents,
            pages_count=pages,
            chunks_count=chunks,
            images_count=images,
            concepts_count=concepts,
            assessment_count=len(assessments),
            questions_answered=answered,
            questions_correct=correct,
            questions_partial=partial,
            questions_incorrect=incorrect,
            average_assessment_score=round(sum(scores) / len(scores), 4) if scores else None,
            overall_mastery=growth.overall_mastery if growth.has_evidence else None,
            mastery_confidence=growth.average_confidence if growth.has_evidence else None,
            growth_status=growth.status if growth.has_evidence else None,
            active_recommendations=rec_counts.get(RecommendationStatus.ACTIVE, 0),
            tutor_conversations=convos,
            tutor_messages=messages,
            last_activity_at=last_activity,
            has_learning_evidence=has_evidence,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "analytics dashboard project_id=%s user_id=%s duration_ms=%s "
            "assessments=%s concepts=%s events_seen=%s",
            project.id,
            user_id,
            duration_ms,
            len(assessments),
            concepts,
            1 if latest else 0,
        )
        return summary

    # ------------------------------------------------------------ activity

    def activity(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        event_types: list[EventType] | None = None,
        window: str = "30d",
        limit: int = 20,
    ) -> list[ActivityItem]:
        """Curated timeline (TIMELINE_TYPES by default) with human summaries
        resolved via bulk name lookups — never N+1, never raw content."""
        project = self._owned_project(user_id, project_id)
        days = self._range_days(window)
        since = self._since(days)
        event_types = self._coerce_types(event_types)
        if event_types is None:
            event_types = list(TIMELINE_TYPES)
        rows, _ = self.events.feed(
            project.id,
            user_id,
            event_types=event_types,
            since=since,
            page=1,
            page_size=min(max(limit, 1), 100),
        )
        names = self._resolve_names(user_id, project, rows)
        return [
            ActivityItem(
                id=event.id,
                event_type=event.event_type,
                created_at=event.created_at,
                resource_id=event.entity_id,
                metadata=sanitize_payload(event.payload),
                summary=self._summarize(event, names),
            )
            for event in rows
        ]

    def activity_by_day(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, window: str = "30d"
    ) -> list[ActivityDay]:
        """Contiguous UTC day series (zero-filled) for bounded ranges; sparse
        points for all-time (never fabricate a giant zero series)."""
        project = self._owned_project(user_id, project_id)
        days = self._range_days(window)
        since = self._since(days)
        counts = {
            self._day_label(day): total
            for day, total in self.events.count_by_day(project.id, user_id, since=since)
        }
        if days is None:
            return [ActivityDay(date=day, count=counts[day]) for day in sorted(counts)]
        now = utcnow()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        series = []
        for back in range(days - 1, -1, -1):
            day = (now - timedelta(days=back)).date().isoformat()
            series.append(ActivityDay(date=day, count=counts.get(day, 0)))
        return series

    def mastery_trend(self, *, user_id: uuid.UUID, project_id: uuid.UUID, limit: int = 30):
        """Assessment-score trajectory, reusing the growth history contract
        (no duplicate trend computation)."""
        from app.services.growth_service import GrowthService

        project = self._owned_project(user_id, project_id)
        return GrowthService(self.session, settings=self.settings).history(
            user_id=user_id, project_id=project.id, limit=min(max(limit, 1), 100)
        )

    # ------------------------------------------------------------ internals

    def global_summary(self, *, user_id: uuid.UUID) -> dict:
        """User-scoped cross-project aggregates. Every query is a COUNT/GROUP
        BY over the user's own projects — never another user's data."""
        from app.models.enums import GrowthStatus, MaterialStatus, RecommendationStatus
        from app.models.intelligence import Growth, Mastery, Recommendation
        from app.models.knowledge import Concept
        from app.models.materials import Material
        from app.models.ops import Event
        from app.models.tutor import Conversation, Message

        s = self.session
        project_ids = list(
            s.scalars(
                sa.select(Project.id).where(
                    Project.owner_id == user_id, Project.archived_at.is_(None)
                )
            ).all()
        )
        if not project_ids:
            return {
                "projects": 0,
                "materials": 0,
                "materials_ready": 0,
                "assessments": 0,
                "questions_answered": 0,
                "tutor_messages": 0,
                "mastery_avg": 0.0,
                "mastery_concepts": 0,
                "attention": [],
                "active_recommendations": 0,
                "recent_project_ids": [],
                "last_activity_at": None,
            }
        # One round trip for both material counts: the app runs far from the
        # database (Neon), so each saved round trip is ~0.3-0.5s of page time.
        mat_total, mat_ready = s.execute(
            sa.select(
                sa.func.count(),
                sa.func.sum(sa.case((Material.status == MaterialStatus.READY, 1), else_=0)),
            )
            .select_from(Material)
            .where(Material.project_id.in_(project_ids))
        ).one()
        materials = mat_total or 0
        ready = int(mat_ready or 0)
        assessments = s.scalars(
            sa.select(Assessment).where(
                Assessment.user_id == user_id, Assessment.project_id.in_(project_ids)
            )
        ).all()
        answered = sum(
            int(e.get("questions_seen", 0) or 0)
            for a in assessments
            for e in (a.concept_results or [])
        )
        mastery_avg, mastery_count = s.execute(
            sa.select(
                sa.func.avg(Mastery.score),
                sa.func.count(),
            ).where(Mastery.user_id == user_id, Mastery.project_id.in_(project_ids))
        ).one()
        mastery_count = mastery_count or 0
        att_rows = s.execute(
            sa.select(Growth.project_id, Concept.name, Growth.change_score)
            .join(Concept, Concept.id == Growth.concept_id)
            .where(
                Growth.user_id == user_id,
                Growth.project_id.in_(project_ids),
                Growth.status == GrowthStatus.REQUIRING_ATTENTION,
            )
            .order_by(Growth.change_score.asc())
            .limit(5)
        ).all()
        active_recs = (
            s.scalar(
                sa.select(sa.func.count())
                .select_from(Recommendation)
                .where(
                    Recommendation.user_id == user_id,
                    Recommendation.project_id.in_(project_ids),
                    Recommendation.status == RecommendationStatus.ACTIVE,
                )
            )
            or 0
        )
        tutor_msgs = (
            s.scalar(
                sa.select(sa.func.count())
                .select_from(Message)
                .join(
                    Conversation,
                    Conversation.id == Message.conversation_id,
                )
                .where(Conversation.project_id.in_(project_ids))
            )
            or 0
        )
        recent_projects = list(
            s.scalars(
                sa.select(Project.id)
                .where(Project.id.in_(project_ids))
                .order_by(Project.updated_at.desc())
                .limit(5)
            ).all()
        )
        last_ev = s.scalars(
            sa.select(Event)
            .where(
                sa.or_(
                    Event.user_id == user_id,
                    Event.project_id.in_(project_ids),
                )
            )
            .order_by(Event.created_at.desc())
            .limit(1)
        ).all()
        return {
            "projects": len(project_ids),
            "materials": materials,
            "materials_ready": ready,
            "assessments": len(assessments),
            "questions_answered": answered,
            "tutor_messages": tutor_msgs,
            "mastery_avg": round(float(mastery_avg or 0), 1),
            "mastery_concepts": mastery_count,
            "attention": [
                {"project_id": str(p), "concept": n, "change": round(float(c or 0), 1)}
                for p, n, c in att_rows
            ],
            "active_recommendations": active_recs,
            "recent_project_ids": [str(p) for p in recent_projects],
            "last_activity_at": last_ev[0].created_at if last_ev else None,
        }

    def home(self, *, user_id: uuid.UUID) -> dict:
        """Continue-learning home: most recent project + its next action,
        recent projects, honest progress, attention, recommended action."""
        from app.models.enums import RecommendationStatus
        from app.models.intelligence import Recommendation
        from app.models.materials import Material

        s = self.session
        summary = self.global_summary(user_id=user_id)
        projects = list(
            s.scalars(
                sa.select(Project)
                .where(Project.owner_id == user_id, Project.archived_at.is_(None))
                .order_by(Project.updated_at.desc())
                .limit(5)
            ).all()
        )
        continue_learning = None
        if projects:
            current = projects[0]
            top_rec = s.scalars(
                sa.select(Recommendation)
                .where(
                    Recommendation.user_id == user_id,
                    Recommendation.project_id == current.id,
                    Recommendation.status == RecommendationStatus.ACTIVE,
                )
                .order_by(Recommendation.priority.desc())
                .limit(1)
            ).one_or_none()
            if top_rec is None:
                top_rec = s.scalars(
                    sa.select(Recommendation)
                    .where(
                        Recommendation.user_id == user_id,
                        Recommendation.project_id.in_([p.id for p in projects[1:]] or [current.id]),
                        Recommendation.status == RecommendationStatus.ACTIVE,
                    )
                    .order_by(Recommendation.priority.desc())
                    .limit(1)
                ).one_or_none()
            mat_count = (
                s.scalar(
                    sa.select(sa.func.count())
                    .select_from(Material)
                    .where(Material.project_id == current.id)
                )
                or 0
            )
            if top_rec is not None:
                action = {
                    "kind": "recommendation",
                    "title": top_rec.title,
                    "reason": top_rec.reason,
                    "project_id": str(top_rec.project_id),
                    "recommendation_id": str(top_rec.id),
                }
            elif mat_count == 0:
                action = {
                    "kind": "upload_material",
                    "title": "Upload your first material",
                    "reason": f"{current.name} has no materials yet.",
                    "project_id": str(current.id),
                    "recommendation_id": None,
                }
            else:
                action = {
                    "kind": "take_quiz",
                    "title": "Take a quiz",
                    "reason": f"Check understanding in {current.name}.",
                    "project_id": str(current.id),
                    "recommendation_id": None,
                }
            continue_learning = {
                "project_id": str(current.id),
                "project_name": current.name,
                "space_id": str(current.space_id),
                "materials": mat_count,
                "next_action": action,
            }
        return {
            "continue_learning": continue_learning,
            "recent_projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "space_id": str(p.space_id),
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ],
            "progress": {
                "projects": summary["projects"],
                "materials": summary["materials"],
                "materials_ready": summary["materials_ready"],
                "assessments": summary["assessments"],
                "questions_answered": summary["questions_answered"],
                "mastery_avg": summary["mastery_avg"],
                "mastery_concepts": summary["mastery_concepts"],
            },
            "attention": summary["attention"],
            "recommended_action": (continue_learning["next_action"] if continue_learning else None),
        }

    def _owned_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        if self.session.get(User, user_id) is None:
            raise NotFoundError("User not found.")
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    @staticmethod
    def _coerce_types(
        event_types: list[EventType] | list[str] | None,
    ) -> list[EventType] | None:
        if event_types is None:
            return None
        coerced = []
        for item in event_types:
            if isinstance(item, EventType):
                coerced.append(item)
                continue
            try:
                coerced.append(EventType(str(item)))
            except ValueError as e:
                raise BadRequestError(f"Unknown event type: {item}.") from e
        return coerced

    @staticmethod
    def _range_days(window: str) -> int | None:
        if window not in RANGE_DAYS:
            raise BadRequestError(f"Unknown range: {window}. Use one of 7d/30d/90d/all.")
        return RANGE_DAYS[window]

    @staticmethod
    def _since(days: int | None):
        if days is None:
            return None
        return utcnow() - timedelta(days=days)

    @staticmethod
    def _day_label(day: object) -> str:
        return str(day)[:10]

    def _resolve_names(self, user_id: uuid.UUID, project, events) -> dict[str, str]:
        """Bulk display-name lookups per entity kind (4 indexed IN queries
        max, regardless of page size). Unknown ids stay unresolved (no leak)."""
        material_ids = {
            e.payload["material_id"]
            for e in events
            if isinstance(e.payload, dict) and e.payload.get("material_id")
        }
        concept_ids = {
            e.payload["concept_id"]
            for e in events
            if isinstance(e.payload, dict) and e.payload.get("concept_id")
        }
        quiz_ids = {
            e.payload["quiz_id"]
            for e in events
            if isinstance(e.payload, dict) and e.payload.get("quiz_id")
        }
        names: dict[str, str] = {}
        if material_ids:
            for material in self.materials.get_many_for_project(
                self._uuids(material_ids), project.id
            ):
                names[f"material:{material.id}"] = material.name
        if concept_ids:
            for concept in self.concepts.get_many_for_project(self._uuids(concept_ids), project.id):
                names[f"concept:{concept.id}"] = concept.name
        if quiz_ids:
            from app.repositories.assessments import QuizRepository

            for quiz in QuizRepository(self.session).get_many_for_project(
                self._uuids(quiz_ids), project.id
            ):
                names[f"quiz:{quiz.id}"] = quiz.title
        rec_ids = [
            e.entity_id
            for e in events
            if e.entity_type == "recommendation" and e.entity_id is not None
        ]
        if rec_ids:
            for rec in self.recommendations.get_many_for_project(rec_ids, project.id, user_id):
                names[f"recommendation:{rec.id}"] = rec.title
        assessments = {
            e.entity_id for e in events if e.entity_type == "assessment" and e.entity_id is not None
        }
        if assessments:
            rows = self.session.scalars(
                sa.select(Assessment).where(
                    Assessment.id.in_(list(assessments)),
                    Assessment.project_id == project.id,
                    Assessment.user_id == user_id,
                )
            ).all()
            for assessment in rows:
                names[f"assessment:{assessment.id}"] = (
                    f"{assessment.score:.0f}%" if assessment.score is not None else "assessment"
                )
        return names

    @staticmethod
    def _uuids(values: set) -> list[uuid.UUID]:
        """Keep only parseable ids as UUID objects (UUID columns reject
        plain strings on SQLite)."""
        parsed = []
        for value in values:
            try:
                parsed.append(uuid.UUID(str(value)))
            except (ValueError, AttributeError, TypeError):
                continue
        return parsed

    def _summarize(self, event, names: dict[str, str]) -> str:
        """Human-readable one-liners from safe metadata + resolved names.
        Never raw payloads, never private content."""
        payload = event.payload if isinstance(event.payload, dict) else {}
        etype = event.event_type
        if etype == EventType.PROJECT_CREATED:
            return f"Created project — {payload.get('name', 'project')}"
        if etype == EventType.MATERIAL_UPLOADED:
            return f"Uploaded — {payload.get('name', 'material')}"
        if etype == EventType.MATERIAL_READY:
            return f"Material ready — {payload.get('name', 'material')}"
        if etype == EventType.MATERIAL_FAILED:
            return f"Processing failed — {payload.get('name', 'material')}"
        if etype == EventType.CONVERSATION_CREATED:
            return "Started a tutor conversation"
        if etype == EventType.TUTOR_MESSAGE:
            return "Asked the tutor"
        if etype == EventType.QUIZ_CREATED:
            return "Created a quiz"
        if etype == EventType.QUIZ_STARTED:
            title = names.get(f"quiz:{payload.get('quiz_id')}", "")
            return f"Started quiz — {title}" if title else "Started a quiz"
        if etype == EventType.ASSESSMENT_COMPLETED:
            score = payload.get("score")
            if isinstance(score, (int, float)):
                return f"Completed assessment — {float(score):.0f}%"
            return "Completed an assessment"
        if etype == EventType.MASTERY_UPDATED:
            name = names.get(f"concept:{payload.get('concept_id')}", "")
            return f"Mastery updated — {name}" if name else "Mastery updated"
        if etype == EventType.RECOMMENDATION_GENERATED:
            title = names.get(f"recommendation:{event.entity_id}", "")
            return f"Recommendation generated — {title}" if title else "Recommendation generated"
        label = str(etype.value if isinstance(etype, EventType) else etype)
        return label.replace("_", " ").title()
