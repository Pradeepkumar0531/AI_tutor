"""Growth interpretive layer (Prompt 10): project-level progress derived from
persisted Mastery state. No new scoring algorithm — Growth INTERPRETS Prompt
9's deterministic estimates; Mastery remains the source of truth.

Two grains, both honest:
- Per-concept ``Growth`` rows (existing Prompt 2 table) refreshed on each
  assessment completion: trajectory + change vs previous + one-line summary.
- Project aggregate computed live on read (never stale, nothing to migrate):
  overall mastery, confidence, status distribution, assessment/question
  counts, cold-start flag.
- History is calculated from immutable assessments (no snapshot table, no
  high-volume records): assessment score trajectory for the chart.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import GrowthStatus, MasteryTrend
from app.models.intelligence import Mastery
from app.repositories.assessments import AssessmentRepository
from app.repositories.intelligence import EventRepository, GrowthRepository, MasteryRepository
from app.repositories.knowledge import ConceptRepository
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.growth")

# Interpretation policy (documented constants, not user input).
LOW_MASTERY = 0.5  # below + evidence: needs attention
DECLINE_MASTERY_CAP = 0.6  # declining below this: needs attention
MIN_OBSERVATIONS_FOR_ATTENTION = 2


def _clamp01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


@dataclass
class ProjectGrowth:
    """Project-level growth aggregate (computed live, 0-1 scale)."""

    project_id: uuid.UUID
    status: GrowthStatus
    has_evidence: bool
    overall_mastery: float = 0.0
    average_confidence: float = 0.0
    concepts_improving: int = 0
    concepts_stable: int = 0
    concepts_requiring_attention: int = 0
    assessed_concepts: int = 0
    assessment_count: int = 0
    questions_answered: int = 0
    updated_at: datetime | None = None


@dataclass
class GrowthHistoryPoint:
    date: datetime
    score: float
    assessment_id: uuid.UUID


@dataclass
class ConceptGrowth:
    concept_id: uuid.UUID
    concept_name: str
    status: GrowthStatus
    mastery_score: float
    confidence: float
    trend: MasteryTrend
    change_score: float | None
    summary: str


def concept_status(*, mastery: float, trend: MasteryTrend, observations: int) -> GrowthStatus:
    """Shared per-concept rule (rows and live aggregate agree by construction).
    Attention requires evidence — a single weak observation is cold start,
    not failure."""
    mastery = _clamp01(mastery)
    if (mastery < LOW_MASTERY and observations >= MIN_OBSERVATIONS_FOR_ATTENTION) or (
        trend == MasteryTrend.DECLINING and mastery < DECLINE_MASTERY_CAP
    ):
        return GrowthStatus.REQUIRING_ATTENTION
    if trend == MasteryTrend.IMPROVING:
        return GrowthStatus.IMPROVING
    return GrowthStatus.STABLE


def project_status(*, improving: int, attention: int, assessed: int) -> GrowthStatus:
    """Project rule: attention is meaningful at 2+, or 1-of-≤2 (a lone weak
    concept in a tiny evidence base still deserves attention); improving needs
    progress with nothing alarming; otherwise stable. Zero evidence is STABLE
    with has_evidence=False — never failure."""
    if assessed <= 0:
        return GrowthStatus.STABLE
    if attention >= 2 or (attention == 1 and assessed <= 2):
        return GrowthStatus.REQUIRING_ATTENTION
    if improving >= 1 and attention == 0:
        return GrowthStatus.IMPROVING
    return GrowthStatus.STABLE


class GrowthService(BaseService):
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.growth = GrowthRepository(session)
        self.mastery_repo = MasteryRepository(session)
        self.assessments = AssessmentRepository(session)
        self.concepts = ConceptRepository(session)
        self.events = EventRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------ refresh

    def refresh_after_assessment(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, assessment_id: uuid.UUID | None = None
    ) -> ProjectGrowth:
        """Rewrite per-concept growth rows from current mastery, then return
        the live aggregate. Upserts converge on retry after a concurrent
        insert race (unique backstop)."""
        last_error: Exception | None = None
        for _ in range(2):
            try:
                return self._refresh(user_id=user_id, project_id=project_id)
            except IntegrityError as e:
                last_error = e
                log.warning("growth refresh race, retrying project=%s", project_id)
        raise ConflictError("Growth refresh conflicted, please retry.") from last_error

    @transactional
    def _refresh(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> ProjectGrowth:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        rows = list(
            self.session.scalars(
                sa.select(Mastery).where(
                    Mastery.user_id == user_id, Mastery.project_id == project.id
                )
            )
        )
        # Batched per-concept reads: one concepts query + one counts query +
        # one latest-observation query instead of three round trips per concept.
        concepts = {
            c.id: c
            for c in self.concepts.get_many_for_project(
                [m.concept_id for m in rows], project.id
            )
        }
        counts = self.mastery_repo.history_counts([m.id for m in rows])
        latest = self.mastery_repo.latest_history([m.id for m in rows])
        for mastery in rows:
            concept = concepts.get(mastery.concept_id)
            name = concept.name if concept is not None else "Concept"
            observations = counts.get(mastery.id, 0)
            status = concept_status(
                mastery=mastery.score / 100,
                trend=mastery.trend,
                observations=observations,
            )
            change = self._delta_of(latest.get(mastery.id))
            summary = self._summarize(
                name=name,
                mastery=mastery.score / 100,
                trend=mastery.trend,
                status=status,
                observations=observations,
            )
            self.growth.refresh(
                user_id=user_id,
                project_id=project.id,
                concept_id=mastery.concept_id,
                status=status,
                change_score=change,
                summary=summary,
            )
        self.session.flush()
        return self._aggregate(user_id=user_id, project_id=project.id)

    @staticmethod
    def _delta_of(latest) -> float | None:
        """Score delta of the newest observation vs its predecessor."""
        if latest is None:
            return None
        previous = latest.previous_score if latest.previous_score is not None else latest.score
        return round((latest.score - previous) / 100, 4)

    def _latest_delta(self, mastery_id: uuid.UUID) -> float | None:
        history = self.mastery_repo.history_for_mastery(mastery_id, limit=1)
        if not history:
            return None
        return self._delta_of(history[0])

    @staticmethod
    def _summarize(
        *, name: str, mastery: float, trend: MasteryTrend, status: GrowthStatus, observations: int
    ) -> str:
        trend_word = {
            MasteryTrend.IMPROVING: "trending up",
            MasteryTrend.DECLINING: "trending down",
            MasteryTrend.STABLE: "steady",
        }[trend]
        base = (
            f"{name}: mastery {mastery:.0%}, {trend_word} "
            f"across {observations} assessed snapshot{'s' if observations != 1 else ''}."
        )
        if status == GrowthStatus.REQUIRING_ATTENTION:
            return base + " Needs attention — review and practice this concept."
        if status == GrowthStatus.IMPROVING:
            return base + " On track — keep going."
        return base + " On track."

    # ------------------------------------------------------------ reads

    def project_growth(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> ProjectGrowth:
        """Read-only aggregate (no writes): safe for every GET."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self._aggregate(user_id=user_id, project_id=project.id)

    def _aggregate(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> ProjectGrowth:
        masteries = list(
            self.session.scalars(
                sa.select(Mastery).where(
                    Mastery.user_id == user_id, Mastery.project_id == project_id
                )
            )
        )
        assessments = self.assessments.recent_for_project_user(project_id, user_id, limit=200)
        questions = 0
        for assessment in assessments:
            for entry in assessment.concept_results or []:
                try:
                    questions += int(entry.get("questions_seen", 0) or 0)
                except (ValueError, TypeError, AttributeError):
                    continue
        if not masteries:
            return ProjectGrowth(
                project_id=project_id,
                status=GrowthStatus.STABLE,
                has_evidence=False,
                assessment_count=len(assessments),
                questions_answered=questions,
                updated_at=None,
            )
        counts = self.mastery_repo.history_counts([m.id for m in masteries])
        improving = stable = attention = 0
        for mastery in masteries:
            observations = counts.get(mastery.id, 0)
            status = concept_status(
                mastery=mastery.score / 100, trend=mastery.trend, observations=observations
            )
            if status == GrowthStatus.REQUIRING_ATTENTION:
                attention += 1
            elif status == GrowthStatus.IMPROVING:
                improving += 1
            else:
                stable += 1
        overall = sum(m.score / 100 for m in masteries) / len(masteries)
        confidence = sum(m.confidence for m in masteries) / len(masteries)
        updated = max((m.updated_at for m in masteries if m.updated_at), default=None)
        return ProjectGrowth(
            project_id=project_id,
            status=project_status(
                improving=improving, attention=attention, assessed=len(masteries)
            ),
            has_evidence=True,
            overall_mastery=round(_clamp01(overall), 4),
            average_confidence=round(_clamp01(confidence), 4),
            concepts_improving=improving,
            concepts_stable=stable,
            concepts_requiring_attention=attention,
            assessed_concepts=len(masteries),
            assessment_count=len(assessments),
            questions_answered=questions,
            updated_at=updated,
        )

    def concept_growth(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> list[ConceptGrowth]:
        """Per-concept growth views for the UI distribution (live derivation;
        rows are the persisted trail)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        masteries = list(
            self.session.scalars(
                sa.select(Mastery).where(
                    Mastery.user_id == user_id, Mastery.project_id == project.id
                )
            )
        )
        views = []
        concepts = {
            c.id: c
            for c in self.concepts.get_many_for_project(
                [m.concept_id for m in masteries], project.id
            )
        }
        counts = self.mastery_repo.history_counts([m.id for m in masteries])
        latest = self.mastery_repo.latest_history([m.id for m in masteries])
        for mastery in masteries:
            concept = concepts.get(mastery.concept_id)
            if concept is None:
                continue
            observations = counts.get(mastery.id, 0)
            views.append(
                ConceptGrowth(
                    concept_id=concept.id,
                    concept_name=concept.name,
                    status=concept_status(
                        mastery=mastery.score / 100,
                        trend=mastery.trend,
                        observations=observations,
                    ),
                    mastery_score=round(_clamp01(mastery.score / 100), 4),
                    confidence=round(_clamp01(mastery.confidence), 4),
                    trend=mastery.trend,
                    change_score=self._delta_of(latest.get(mastery.id)),
                    summary=self._summarize(
                        name=concept.name,
                        mastery=mastery.score / 100,
                        trend=mastery.trend,
                        status=concept_status(
                            mastery=mastery.score / 100,
                            trend=mastery.trend,
                            observations=observations,
                        ),
                        observations=observations,
                    ),
                )
            )
        views.sort(key=lambda v: v.concept_name.lower())
        return views

    def history(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, limit: int = 100
    ) -> list[GrowthHistoryPoint]:
        """Calculated trajectory from immutable assessments (newest last for
        charts). No snapshot table: bounded, never stale, never fabricated."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        points = []
        for assessment in self.assessments.recent_for_project_user(
            project.id, user_id, limit=limit
        ):
            if assessment.completed_at is None or assessment.score is None:
                continue
            points.append(
                GrowthHistoryPoint(
                    date=assessment.completed_at,
                    score=round(_clamp01(assessment.score / 100), 4),
                    assessment_id=assessment.id,
                )
            )
        points.reverse()
        return points
