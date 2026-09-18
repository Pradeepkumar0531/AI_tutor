"""Mastery Engine (Prompt 9): deterministic, explainable per-concept estimates.

Pipeline: ``AssessmentResult`` -> per-concept evidence -> EWMA-style update
with bounded evidence weight + time decay -> ``Mastery`` row + immutable
``MasteryHistory`` row + ``MASTERY_UPDATED`` event. No LLM anywhere: every
number derives from stored assessment evidence with a documented formula.

Scale note: ``Mastery.score``/``MasteryHistory.score``/``previous_score``
persist 0-100 (existing schema + CHECKs); the algorithm works 0-1 and the
API presents 0-1. The mapping is exactly ``/100``, applied in one place.

Algorithm (per assessed concept):
  observation o      = clamp(concept.normalized_score)            # 0-1
  questions q        = max(questions_seen, 1)
  age_days           = max(0, (assessment.completed_at - last_assessed_at).days)
  decay              = exp(-recency_lambda * age_days)            # 1 when fresh
  old_decayed        = baseline + (old - baseline) * decay
  conf_decayed       = conf_old * decay
  alpha              = min(ALPHA_MAX, ALPHA_BASE
                           + ALPHA_PER_QUESTION * (q - 1)
                           + ALPHA_HISTORY_BONUS * min(prior_obs, HISTORY_CAP))
  new                = (1 - alpha) * old_decayed + alpha * o      # never latest-score
  conf               = 1 - (1 - conf_decayed)
                           * (1 - min(1, q / CONF_SATURATION) * CONF_UPDATE_MAX)
  trend              = windowed mean comparison over post-update history

Properties: bounded 0-1 always; old evidence never fully discarded
(alpha <= 0.5); repeated observations raise confidence with diminishing
returns; partial scores contribute partially; cold start = (baseline, low
confidence), never 0 or 1.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.assessment import Assessment
from app.models.enums import EventType, GrowthStatus, MasterySource, MasteryTrend
from app.models.intelligence import Growth, Mastery, MasteryHistory
from app.repositories.intelligence import (
    EventRepository,
    GrowthRepository,
    MasteryRepository,
)
from app.repositories.knowledge import ConceptRepository
from app.repositories.projects import ProjectRepository
from app.services.assessment_contracts import AssessmentResult, ConceptPerformance
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.mastery")

# Update-shape constants (documented, not user-configurable; the six
# MASTERY_* Settings carry the tunable policy).
ALPHA_BASE = 0.25
ALPHA_PER_QUESTION = 0.05
ALPHA_HISTORY_BONUS = 0.02
HISTORY_CAP = 10
CONF_SATURATION = 4
CONF_UPDATE_MAX = 0.5


def _clamp01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


@dataclass
class MasteryUpdate:
    """One concept transition applied from an assessment (0-1 scale)."""

    mastery: Mastery
    concept_id: uuid.UUID
    previous_score: float
    new_score: float
    confidence: float


@dataclass
class MasteryExplanation:
    """Deterministic, stored-data-only explanation for Growth UI (Prompt 10).
    No LLM involved."""

    concept_id: uuid.UUID
    concept_name: str
    mastery_score: float
    confidence: float
    trend: MasteryTrend
    evidence_assessments: int
    evidence_questions: int
    recent_performance: list[str] = field(default_factory=list)
    contributing_assessments: list[uuid.UUID] = field(default_factory=list)
    has_evidence: bool = False
    updated_at: datetime | None = None


class MasteryService(BaseService):
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.mastery = MasteryRepository(session)
        self.growth = GrowthRepository(session)
        self.events = EventRepository(session)
        self.projects = ProjectRepository(session)
        self.concepts = ConceptRepository(session)

    @transactional
    def record_observation(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        score: float,
        confidence: float = 0.0,
        source: MasterySource,
        trend: MasteryTrend = MasteryTrend.STABLE,
        assessment_id: uuid.UUID | None = None,
    ) -> tuple[Mastery, MasteryHistory]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        concept = ConceptRepository(self.session).get_for_project(concept_id, project.id)
        if concept is None:
            raise NotFoundError("Concept not found.")
        mastery, history = self.mastery.record_observation(
            user_id=user_id,
            project_id=project.id,
            concept_id=concept.id,
            score=score,
            confidence=confidence,
            source=source,
            trend=trend,
            assessment_id=assessment_id,
        )
        self.session.flush()
        self.events.append(
            event_type=EventType.MASTERY_UPDATED,
            user_id=user_id,
            project_id=project.id,
            entity_type="mastery",
            entity_id=mastery.id,
            payload={"concept_id": str(concept.id), "score": score},
        )
        return mastery, history

    @transactional
    def refresh_growth(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        status: GrowthStatus,
        change_score: float | None = None,
        summary: str | None = None,
    ) -> Growth:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self.growth.refresh(
            user_id=user_id,
            project_id=project.id,
            concept_id=concept_id,
            status=status,
            change_score=change_score,
            summary=summary,
        )

    # ------------------------------------------------------------ assessment input

    def update_from_assessment(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        assessment_result: AssessmentResult,
    ) -> list[MasteryUpdate]:
        """Apply one completed assessment to the concepts it represents.

        Retried safely: the (mastery, assessment) unique guard makes a second
        application a no-op. Only concepts in ``concept_results`` are touched.
        """
        last_error: Exception | None = None
        for _ in range(2):
            try:
                return self._update_once(
                    user_id=user_id, project_id=project_id, assessment_result=assessment_result
                )
            except IntegrityError as e:
                # Lost a race (duplicate mastery row or history row): the
                # transaction rolled back; re-read finds the winner and skips
                # applied pairs, converging to exactly-once state.
                last_error = e
                log.warning(
                    "mastery update race, retrying assessment=%s",
                    assessment_result.assessment_id,
                )
        raise ConflictError("Mastery update conflicted, please retry.") from last_error

    @transactional
    def _update_once(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        assessment_result: AssessmentResult,
    ) -> list[MasteryUpdate]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        assessment = self.session.get(Assessment, assessment_result.assessment_id)
        if (
            assessment is None
            or assessment.user_id != user_id
            or assessment.project_id != project.id
        ):
            raise NotFoundError("Assessment not found.")
        applied: list[MasteryUpdate] = []
        for perf in assessment_result.concept_results:
            concept = self.concepts.get_for_project(perf.concept_id, project.id)
            if concept is None:
                raise NotFoundError("Concept not found.")
            update = self._apply_concept(
                user_id=user_id,
                project_id=project.id,
                concept_id=concept.id,
                observation=_clamp01(perf.normalized_score),
                questions_seen=max(perf.questions_seen, 1),
                assessment=assessment,
            )
            if update is not None:
                applied.append(update)
        return applied

    def _apply_concept(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        observation: float,
        questions_seen: int,
        assessment,
    ) -> MasteryUpdate | None:
        """Single-concept EWMA update + history + event. Returns None when
        this assessment was already applied (idempotent replay)."""
        settings = self.settings
        baseline = _clamp01(settings.mastery_baseline)
        mastery = self.mastery.get_for_update(
            user_id=user_id, project_id=project_id, concept_id=concept_id
        )
        if mastery is None:
            mastery = self.mastery.add(
                Mastery(
                    user_id=user_id,
                    project_id=project_id,
                    concept_id=concept_id,
                    score=round(baseline * 100, 2),
                    confidence=settings.mastery_initial_confidence,
                )
            )
            self.session.flush()
        if self.mastery.history_exists(mastery.id, assessment.id):
            return None
        old = _clamp01(mastery.score / 100)
        conf_old = _clamp01(mastery.confidence)
        completed_at = assessment.completed_at or assessment.created_at
        age_days = 0
        if mastery.last_assessed_at is not None and completed_at is not None:
            age_days = max(0, (completed_at.date() - mastery.last_assessed_at.date()).days)
        decay = math.exp(-max(settings.mastery_recency_lambda, 0.0) * age_days)
        old_decayed = baseline + (old - baseline) * decay
        conf_decayed = conf_old * decay
        prior_obs = self.mastery.history_count(mastery.id)
        alpha = min(
            _clamp01(settings.mastery_max_evidence_weight),
            ALPHA_BASE
            + ALPHA_PER_QUESTION * (questions_seen - 1)
            + ALPHA_HISTORY_BONUS * min(prior_obs, HISTORY_CAP),
        )
        new = _clamp01((1 - alpha) * old_decayed + alpha * observation)
        conf = _clamp01(
            1
            - (1 - conf_decayed)
            * (1 - min(1.0, questions_seen / CONF_SATURATION) * CONF_UPDATE_MAX)
        )
        mastery.score = round(new * 100, 2)
        mastery.confidence = round(conf, 4)
        mastery.last_assessed_at = completed_at
        history = MasteryHistory(
            mastery_id=mastery.id,
            score=mastery.score,
            confidence=mastery.confidence,
            source=MasterySource.ASSESSMENT,
            assessment_id=assessment.id,
            previous_score=round(old * 100, 2),
        )
        self.session.add(history)
        self.session.flush()
        mastery.trend = self._trend_for(mastery)
        self.session.flush()
        self.events.append(
            event_type=EventType.MASTERY_UPDATED,
            user_id=user_id,
            project_id=project_id,
            entity_type="mastery",
            entity_id=mastery.id,
            payload={
                "concept_id": str(concept_id),
                "assessment_id": str(assessment.id),
                "previous_score": round(old, 4),
                "new_score": round(new, 4),
                "confidence": round(conf, 4),
            },
        )
        return MasteryUpdate(
            mastery=mastery,
            concept_id=concept_id,
            previous_score=round(old, 4),
            new_score=round(new, 4),
            confidence=round(conf, 4),
        )

    def _trend_for(self, mastery: Mastery) -> MasteryTrend:
        """Windowed mean comparison over post-update history (oldest→newest).
        Fewer than 3 observations → STABLE (never a single answer)."""
        settings = self.settings
        window = min(max(settings.mastery_trend_window, 3), 50)
        history = self.mastery.history_for_mastery(mastery.id, limit=window)
        if len(history) < 3:
            return MasteryTrend.STABLE
        scores = [_clamp01(h.score / 100) for h in history]
        half = len(scores) // 2
        earlier = sum(scores[:half]) / half
        later = sum(scores[half:]) / (len(scores) - half)
        threshold = max(settings.mastery_trend_threshold, 0.0)
        if later - earlier > threshold:
            return MasteryTrend.IMPROVING
        if earlier - later > threshold:
            return MasteryTrend.DECLINING
        return MasteryTrend.STABLE

    # ------------------------------------------------------------ reads

    def list_mastery(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        sort: str = "lowest",
    ) -> tuple[list[dict], int]:
        """Paginated mastery rows with concept names + observation counts.
        Sort: lowest (score asc) | recent (updated desc) | name."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        rows, total = self.mastery.list_for_project(
            project.id, user_id, page=page, page_size=page_size, sort=sort
        )
        counts = self.mastery.history_counts([m.id for m in rows])
        names = {
            c.id: c.name
            for c in self.concepts.get_many_for_project(
                [m.concept_id for m in rows], project.id
            )
        }
        items = []
        for mastery in rows:
            items.append(
                {
                    "mastery": mastery,
                    "concept_name": names.get(mastery.concept_id, ""),
                    "evidence_count": counts.get(mastery.id, 0),
                }
            )
        return items, total

    def mastery_history(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MasteryHistory], int]:
        """Bounded history window, newest first. Unknown concept/project →
        404; known concept without mastery → empty (cold start, not an error)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        concept = self.concepts.get_for_project(concept_id, project.id)
        if concept is None:
            raise NotFoundError("Concept not found.")
        mastery = self.mastery.get_for_user(
            user_id=user_id, project_id=project.id, concept_id=concept.id
        )
        if mastery is None:
            return [], 0
        rows = self.mastery.history_for_mastery(mastery.id, limit=200)
        rows.reverse()  # newest first for the paginated view
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        total = len(rows)
        return rows[(page - 1) * page_size : page * page_size], total

    def scores_for_concepts(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, float]:
        """Current 0-1 mastery for known triples (Prompt 8 strategy input).
        Unknown concepts are absent — never fabricated."""
        estimates: dict[uuid.UUID, float] = {}
        for concept_id in concept_ids:
            mastery = self.mastery.get_for_user(
                user_id=user_id, project_id=project_id, concept_id=concept_id
            )
            if mastery is not None:
                estimates[concept_id] = _clamp01(mastery.score / 100)
        return estimates

    def explain(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> MasteryExplanation:
        """Stored-data-only explanation (no LLM). Cold-start concepts report
        the baseline with has_evidence=False — never 0% as false knowledge."""
        settings = self.settings
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        concept = self.concepts.get_for_project(concept_id, project.id)
        if concept is None:
            raise NotFoundError("Concept not found.")
        mastery = self.mastery.get_for_user(
            user_id=user_id, project_id=project.id, concept_id=concept.id
        )
        if mastery is None:
            return MasteryExplanation(
                concept_id=concept.id,
                concept_name=concept.name,
                mastery_score=_clamp01(settings.mastery_baseline),
                confidence=_clamp01(settings.mastery_initial_confidence),
                trend=MasteryTrend.STABLE,
                evidence_assessments=0,
                evidence_questions=0,
                has_evidence=False,
                updated_at=None,
            )
        history = self.mastery.history_for_mastery(mastery.id, limit=200)
        assessment_ids = [h.assessment_id for h in history if h.assessment_id is not None]
        questions = 0
        recent: list[str] = []
        contributing: list[uuid.UUID] = []
        if assessment_ids:
            assessments = self.session.scalars(
                sa.select(Assessment).where(Assessment.id.in_(assessment_ids))
            ).all()
            by_id = {a.id: a for a in assessments}
            for assessment_id in reversed(assessment_ids):
                assessment = by_id.get(assessment_id)
                if assessment is None:
                    continue
                contributing.append(assessment_id)
                for entry in assessment.concept_results or []:
                    try:
                        if uuid.UUID(str(entry.get("concept_id"))) != concept.id:
                            continue
                    except (ValueError, AttributeError, TypeError):
                        continue
                    questions += int(entry.get("questions_seen", 0) or 0)
                    if not recent:
                        recent = [str(r) for r in (entry.get("recent") or [])][:3]
            contributing = contributing[:5]
        return MasteryExplanation(
            concept_id=concept.id,
            concept_name=concept.name,
            mastery_score=_clamp01(mastery.score / 100),
            confidence=_clamp01(mastery.confidence),
            trend=mastery.trend,
            evidence_assessments=len(history),
            evidence_questions=questions,
            recent_performance=recent,
            contributing_assessments=contributing,
            has_evidence=True,
            updated_at=mastery.updated_at,
        )

    def rebuild_concept(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> Mastery | None:
        """Deterministic service-level rebuild: wipe the triple's rows and
        replay its assessments in (completed_at, id) order. Same inputs always
        yield the same state; immutable assessment records are never touched.
        No route exposes this (Prompt 9 scope)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        concept = self.concepts.get_for_project(concept_id, project.id)
        if concept is None:
            raise NotFoundError("Concept not found.")
        return self._rebuild(user_id=user_id, project_id=project.id, concept_id=concept.id)

    @transactional
    def _rebuild(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> Mastery | None:
        existing = self.mastery.get_for_user(
            user_id=user_id, project_id=project_id, concept_id=concept_id
        )
        if existing is not None:
            self.session.delete(existing)
            self.session.flush()
        assessments = self.session.scalars(
            sa.select(Assessment)
            .where(Assessment.project_id == project_id, Assessment.user_id == user_id)
            .order_by(Assessment.completed_at, Assessment.id)
        ).all()
        mastery: Mastery | None = None
        for assessment in assessments:
            perfs = [
                e
                for e in (assessment.concept_results or [])
                if str(e.get("concept_id")) == str(concept_id)
            ]
            if not perfs:
                continue
            result = AssessmentResult(
                assessment_id=assessment.id,
                quiz_attempt_id=assessment.quiz_attempt_id or assessment.id,
                quiz_id=assessment.quiz_attempt_id or assessment.id,
                total_questions=0,
                answered_count=0,
                correct_count=0,
                partial_count=0,
                incorrect_count=0,
                score=assessment.score or 0.0,
                concept_results=[
                    ConceptPerformance(
                        concept_id=concept_id,
                        concept_name="",
                        questions_seen=int(e.get("questions_seen", 0) or 0),
                        correct_count=int(e.get("correct_count", 0) or 0),
                        partial_count=int(e.get("partial_count", 0) or 0),
                        incorrect_count=int(e.get("incorrect_count", 0) or 0),
                        normalized_score=float(e.get("normalized_score", 0.0) or 0.0),
                        recent=[str(r) for r in (e.get("recent") or [])][:3],
                    )
                    for e in perfs
                ],
            )
            for update in self._update_once(
                user_id=user_id, project_id=project_id, assessment_result=result
            ):
                mastery = update.mastery
        return mastery
