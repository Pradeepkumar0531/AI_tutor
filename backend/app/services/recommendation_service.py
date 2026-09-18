"""Deterministic recommendation engine (Prompt 10).

Eligibility and priority are pure functions of persisted learning state —
no LLM decides anything (wording is fixed templates over structured facts).
Flow per assessment completion: expire resolved ACTIVE rows -> generate from
mastery + recent performance + materials -> dedup -> cap -> persist + event.

Priority (0-100, documented meaning: higher = act sooner):
  40 * (1 - mastery)          # need: lower mastery, stronger pull
+ 20 if declining trend       # trajectory alarm
+ 15 if recent mistakes ("I") # concrete struggle evidence
+ 10 if confidence > 0.5      # evidence-backed, not cold-start noise
+  5 if goal-relevant         # concept named in learning goal/outcome

Rules (all require assessed mastery — cold-start concepts never qualify):
- REVIEW_CONCEPT: recent mistakes/decline + material available.
- PRACTICE_QUIZ: mastery < 0.8 with mistakes, repeated evidence, or clear
  weakness — never for a single positive observation alone.
- STUDY_MATERIAL: mastery < 0.6 without recent mistakes (stale weakness) +
  material available.
- TUTOR_SESSION: declining + mastery < 0.6 (talk it through).
Every type carries concept_id; material types carry a project-verified
material_id. TAKE_ASSESSMENT is intentionally absent: PRACTICE_QUIZ with a
concept focus starts the existing adaptive flow (no new enum values, no new
migration).
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import (
    EventType,
    MasteryTrend,
    RecommendationStatus,
    RecommendationType,
)
from app.models.intelligence import Recommendation
from app.repositories.assessments import AssessmentRepository
from app.repositories.intelligence import (
    EventRepository,
    MasteryRepository,
    RecommendationRepository,
)
from app.repositories.knowledge import ConceptRepository
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.recommendations")

# Generation policy (documented constants, not user input).
RESOLVED_MASTERY = 0.85  # at/above: active weakness recs expire
PRACTICE_BELOW = 0.8
STALE_BELOW = 0.6
TUTOR_BELOW = 0.6
HIGH_CONFIDENCE = 0.5
MAX_ACTIVE_PER_PROJECT = 8
MAX_NEW_PER_REFRESH = 3


class RecommendationService(BaseService):
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.recommendations = RecommendationRepository(session)
        self.mastery_repo = MasteryRepository(session)
        self.assessments = AssessmentRepository(session)
        self.concepts = ConceptRepository(session)
        self.events = EventRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------ refresh

    def refresh_after_assessment(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID | None = None,
    ) -> list[Recommendation]:
        """Expire resolved rows, generate missing ones. Retried once on
        dedup races (unique backstop), converging to no duplicates."""
        last_error: Exception | None = None
        for _ in range(2):
            try:
                return self._refresh_once(
                    user_id=user_id, project_id=project_id, assessment_id=assessment_id
                )
            except IntegrityError as e:
                last_error = e
                log.warning("recommendation refresh race, retrying project=%s", project_id)
        raise ConflictError("Recommendation refresh conflicted, please retry.") from last_error

    @transactional
    def _refresh_once(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID | None,
    ) -> list[Recommendation]:
        from app.models.assessment import Assessment
        from app.models.intelligence import Mastery

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        trigger: Assessment | None = None
        if assessment_id is not None:
            trigger = self.session.get(Assessment, assessment_id)
            if trigger is None or trigger.user_id != user_id or trigger.project_id != project.id:
                raise NotFoundError("Assessment not found.")
        masteries = list(
            self.session.scalars(
                sa.select(Mastery).where(
                    Mastery.user_id == user_id, Mastery.project_id == project.id
                )
            )
        )
        self._expire_resolved(user_id=user_id, project_id=project.id, masteries=masteries)
        active = self.session.scalars(
            sa.select(Recommendation).where(
                Recommendation.user_id == user_id,
                Recommendation.project_id == project.id,
                Recommendation.status == RecommendationStatus.ACTIVE,
            )
        ).all()
        if len(active) >= MAX_ACTIVE_PER_PROJECT:
            return []
        candidates = self._candidates(
            user_id=user_id, project=project, masteries=masteries, trigger=trigger
        )
        created: list[Recommendation] = []
        for candidate in sorted(candidates, key=lambda c: -c["priority"]):
            if len(created) >= MAX_NEW_PER_REFRESH:
                break
            if len(active) + len(created) >= MAX_ACTIVE_PER_PROJECT:
                break
            if self.recommendations.find_active_scope(
                user_id=user_id,
                project_id=project.id,
                concept_id=candidate["concept_id"],
                type=candidate["type"],
            ):
                continue  # identical active scope already exists
            row = self.recommendations.create(
                project_id=project.id,
                user_id=user_id,
                type=candidate["type"],
                title=candidate["title"],
                concept_id=candidate["concept_id"],
                material_id=candidate["material_id"],
                description=candidate["description"],
                reason=candidate["reason"],
                priority=candidate["priority"],
                source_assessment_id=trigger.id if trigger is not None else None,
            )
            self.session.flush()
            self.events.append(
                event_type=EventType.RECOMMENDATION_GENERATED,
                user_id=user_id,
                project_id=project.id,
                entity_type="recommendation",
                entity_id=row.id,
                payload={
                    "type": candidate["type"].value,
                    "concept_id": str(candidate["concept_id"]),
                    "priority": candidate["priority"],
                    "assessment_id": str(trigger.id) if trigger is not None else None,
                },
            )
            created.append(row)
        return created

    def _expire_resolved(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, masteries: list
    ) -> int:
        """ACTIVE rows whose concept now demonstrates strong mastery expire —
        a recommendation must not stay urgent after the learner proved it."""
        expired = 0
        for mastery in masteries:
            if mastery.score / 100 < RESOLVED_MASTERY:
                continue
            rows = self.session.scalars(
                sa.select(Recommendation).where(
                    Recommendation.user_id == user_id,
                    Recommendation.project_id == project_id,
                    Recommendation.concept_id == mastery.concept_id,
                    Recommendation.status == RecommendationStatus.ACTIVE,
                )
            ).all()
            for row in rows:
                self.recommendations.set_status(row, RecommendationStatus.EXPIRED)
                expired += 1
        if expired:
            self.session.flush()
        return expired

    def _candidates(self, *, user_id: uuid.UUID, project, masteries: list, trigger) -> list[dict]:
        from app.services.knowledge_service import KnowledgeService

        knowledge = KnowledgeService(self.session)
        goal_text = f"{project.learning_goal or ''} {project.target_outcome or ''}".lower()
        # Batched per-concept reads: concepts + observation counts + one
        # bounded assessment scan shared across concepts (completion path).
        concepts = {
            c.id: c
            for c in self.concepts.get_many_for_project(
                [m.concept_id for m in masteries], project.id
            )
        }
        counts = self.mastery_repo.history_counts([m.id for m in masteries])
        recent_assessments = self.assessments.recent_for_project_user(
            project.id, user_id, limit=50
        )
        candidates = []
        for mastery in masteries:
            concept = concepts.get(mastery.concept_id)
            if concept is None:
                continue
            m = min(max(mastery.score / 100, 0.0), 1.0)
            conf = min(max(mastery.confidence, 0.0), 1.0)
            observations = counts.get(mastery.id, 0)
            perf = self._latest_perf_from(recent_assessments, concept.id, trigger)
            recent = perf.get("recent", []) if perf else []
            mistakes = "I" in recent
            declining = mastery.trend == MasteryTrend.DECLINING
            goal_relevant = bool(concept.name) and concept.name.lower() in goal_text
            priority = self._priority(
                mastery=m,
                declining=declining,
                mistakes=mistakes,
                confidence=conf,
                goal_relevant=goal_relevant,
            )
            materials = self._concept_materials(knowledge, user_id, project.id, concept.id)
            material = self._first_material(materials)
            evidence = (
                f"mastery {m:.0%} over {observations} assessed snapshot"
                f"{'s' if observations != 1 else ''}"
            )
            if mistakes:
                evidence += f"; recent answers show mistakes ({' '.join(recent)})"
            if declining:
                evidence += "; trending down"
            if m < PRACTICE_BELOW and (mistakes or observations >= 2 or m < STALE_BELOW):
                candidates.append(
                    self._practice(concept, m, conf, priority, evidence, observations)
                )
            if mistakes and material is not None:
                candidates.append(self._review(concept, material, m, priority, evidence, recent))
            if (
                m < STALE_BELOW
                and not mistakes
                and mastery.trend != MasteryTrend.DECLINING
                and material is not None
            ):
                candidates.append(
                    self._study(concept, material, m, priority, evidence, observations)
                )
            if declining and m < TUTOR_BELOW:
                candidates.append(self._tutor_session(concept, m, priority, evidence, recent))
        candidates.extend(self._repeated_mistake_candidates(user_id=user_id, project=project))
        return candidates

    def _repeated_mistake_candidates(self, *, user_id, project) -> list[dict]:
        """Targeted practice for concepts with a recorded repeated-mistake
        pattern (see LearningContextService). Highest priority: the learner
        has proven, more than once, that this exact concept fails. Idempotent
        via the standard find_active_scope dedup in _refresh_once."""
        from app.services.learning_context_service import LearningContextService

        repeated = LearningContextService(self.session).repeated_concept_ids(
            user_id=user_id, project_id=project.id
        )
        if not repeated:
            return []
        names = {
            c.id: c.name
            for c in self.concepts.get_many_for_project(list(repeated), project.id)
        }
        candidates = []
        for cid in repeated:
            name = names.get(cid)
            if name is None:
                continue
            candidates.append(
                {
                    "type": RecommendationType.PRACTICE_QUIZ,
                    "concept_id": cid,
                    "material_id": None,
                    "title": f"Targeted practice: {name}",
                    "description": (f"Focused questions on {name}, where mistakes keep repeating."),
                    "reason": (
                        f"Repeated mistakes on {name} across recent attempts "
                        "(recorded learning-context pattern). "
                        "A short targeted quiz addresses the exact gap."
                    ),
                    "priority": 90,
                }
            )
        return candidates

    @staticmethod
    def _priority(
        *, mastery: float, declining: bool, mistakes: bool, confidence: float, goal_relevant: bool
    ) -> int:
        score = (
            40 * (1 - mastery)
            + (20 if declining else 0)
            + (15 if mistakes else 0)
            + (10 if confidence > HIGH_CONFIDENCE else 0)
            + (5 if goal_relevant else 0)
        )
        return min(max(round(score), 0), 100)

    def _latest_perf(self, user_id, project_id, concept_id, trigger) -> dict | None:
        """Latest C/P/I evidence: triggering assessment first, then newest
        covering assessment (bounded scan)."""
        history = self.assessments.recent_for_project_user(project_id, user_id, limit=50)
        return self._latest_perf_from(history, concept_id, trigger)

    @staticmethod
    def _latest_perf_from(history, concept_id, trigger) -> dict | None:
        for assessment in ([trigger] if trigger is not None else []) + list(history):
            if assessment is None:
                continue
            for entry in assessment.concept_results or []:
                try:
                    if uuid.UUID(str(entry.get("concept_id"))) == concept_id:
                        return entry
                except (ValueError, AttributeError, TypeError):
                    continue
        return None

    def _concept_materials(self, knowledge, user_id, project_id, concept_id) -> list[dict]:
        try:
            _, materials, _, _ = knowledge.get_concept_detail(
                user_id=user_id, project_id=project_id, concept_id=concept_id
            )
            return [m for m in materials if isinstance(m, dict) and m.get("id")]
        except Exception as e:  # noqa: BLE001 - missing materials just narrow types
            log.warning("recommendation material lookup failed err=%s", e)
            return []

    @staticmethod
    def _first_material(materials: list[dict]) -> dict | None:
        """First material with a parseable id, normalized to UUIDs (provenance
        stores string ids; rows need UUID objects)."""
        for entry in materials:
            try:
                material_id = uuid.UUID(str(entry.get("id")))
            except (ValueError, AttributeError, TypeError):
                continue
            return {"id": material_id, "name": str(entry.get("name", ""))}
        return None

    @staticmethod
    def _practice(concept, mastery, confidence, priority, evidence, observations) -> dict:
        return {
            "type": RecommendationType.PRACTICE_QUIZ,
            "concept_id": concept.id,
            "material_id": None,
            "title": f"Practice {concept.name}",
            "description": f"Targeted practice for {concept.name}.",
            "reason": (
                f"{concept.name} sits at {mastery:.0%} mastery ({evidence}). "
                "A short focused quiz is the fastest way to move it."
            ),
            "priority": priority,
        }

    @staticmethod
    def _review(concept, material, mastery, priority, evidence, recent) -> dict:
        return {
            "type": RecommendationType.REVIEW_CONCEPT,
            "concept_id": concept.id,
            "material_id": material["id"],
            "title": f"Review {concept.name}",
            "description": f"Revisit {concept.name} in {material['name']}.",
            "reason": (
                f"Recent work on {concept.name} shows mistakes ({' '.join(recent)}); "
                f"mastery is {mastery:.0%} ({evidence}). "
                f"Review {material['name']} first, then practice."
            ),
            "priority": min(priority + 5, 100),
        }

    @staticmethod
    def _study(concept, material, mastery, priority, evidence, observations) -> dict:
        return {
            "type": RecommendationType.STUDY_MATERIAL,
            "concept_id": concept.id,
            "material_id": material["id"],
            "title": f"Study {material['name']}",
            "description": f"Refresh {concept.name} from source material.",
            "reason": (
                f"{concept.name} rests at {mastery:.0%} ({evidence}) without recent "
                f"mistakes — a forgotten weakness. Re-read {material['name']}, then "
                "take an assessment."
            ),
            "priority": priority,
        }

    @staticmethod
    def _tutor_session(concept, mastery, priority, evidence, recent) -> dict:
        return {
            "type": RecommendationType.TUTOR_SESSION,
            "concept_id": concept.id,
            "material_id": None,
            "title": f"Ask the tutor about {concept.name}",
            "description": f"Talk through {concept.name} with the project tutor.",
            "reason": (
                f"{concept.name} is declining at {mastery:.0%} ({evidence}) — "
                "talking it through with the tutor can unblock you."
            ),
            "priority": priority,
        }

    # ------------------------------------------------------------ reads/lifecycle

    @staticmethod
    def actions_for(rec_type: RecommendationType, *, has_material: bool) -> list[str]:
        """Backend-confirmed capabilities per recommendation (the frontend
        renders only these — never dead-end buttons)."""
        if rec_type == RecommendationType.REVIEW_CONCEPT:
            return ["open_material", "practice_quiz"] if has_material else ["practice_quiz"]
        if rec_type == RecommendationType.PRACTICE_QUIZ:
            return ["practice_quiz"]
        if rec_type == RecommendationType.STUDY_MATERIAL:
            return ["open_material"] if has_material else []
        if rec_type == RecommendationType.TUTOR_SESSION:
            return ["ask_tutor"]
        return []

    def list_active(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Recommendation], int]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self.recommendations.list_active(project.id, user_id, page=page, page_size=page_size)

    def describe_many(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, rows: list[Recommendation]
    ) -> list[dict]:
        """Batched describe for list views: two IN queries instead of two
        round trips per row."""
        from app.models.materials import Material

        concept_ids = list({r.concept_id for r in rows if r.concept_id is not None})
        material_ids = list({r.material_id for r in rows if r.material_id is not None})
        concept_names = (
            {
                c.id: c.name
                for c in self.concepts.get_many_for_project(concept_ids, project_id)
            }
            if concept_ids
            else {}
        )
        material_names: dict = {}
        if material_ids:
            material_names = {
                m.id: m.name
                for m in self.session.scalars(
                    sa.select(Material).where(
                        Material.id.in_(material_ids), Material.project_id == project_id
                    )
                )
            }
        return [
            {
                "row": row,
                "concept_name": concept_names.get(row.concept_id, "") if row.concept_id else "",
                "material_name": material_names.get(row.material_id, "") if row.material_id else "",
                "actions": self.actions_for(
                    row.type,
                    has_material=bool(
                        row.material_id and material_names.get(row.material_id)
                    ),
                ),
            }
            for row in rows
        ]

    def describe(self, *, user_id: uuid.UUID, project_id: uuid.UUID, row: Recommendation) -> dict:
        """Enriched read dict with project-verified concept/material names."""
        concept_name = ""
        if row.concept_id is not None:
            concept = self.concepts.get_for_project(row.concept_id, project_id)
            concept_name = concept.name if concept is not None else ""
        material_name = ""
        if row.material_id is not None:
            from app.repositories.materials import MaterialRepository

            material = MaterialRepository(self.session).get_for_project(row.material_id, project_id)
            material_name = material.name if material is not None else ""
        return {
            "row": row,
            "concept_name": concept_name,
            "material_name": material_name,
            "actions": self.actions_for(row.type, has_material=bool(material_name)),
        }

    def get(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, recommendation_id: uuid.UUID
    ) -> Recommendation:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        row = self.recommendations.get_for_project(recommendation_id, project.id, user_id)
        if row is None:
            raise NotFoundError("Recommendation not found.")
        return row

    def complete(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, recommendation_id: uuid.UUID
    ) -> Recommendation:
        return self._transition(
            user_id=user_id,
            project_id=project_id,
            recommendation_id=recommendation_id,
            to_status=RecommendationStatus.COMPLETED,
        )

    def dismiss(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, recommendation_id: uuid.UUID
    ) -> Recommendation:
        return self._transition(
            user_id=user_id,
            project_id=project_id,
            recommendation_id=recommendation_id,
            to_status=RecommendationStatus.DISMISSED,
        )

    @transactional
    def _transition(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, recommendation_id, to_status
    ) -> Recommendation:
        row = self.get(user_id=user_id, project_id=project_id, recommendation_id=recommendation_id)
        if row.status != RecommendationStatus.ACTIVE:
            raise ConflictError(f"Recommendation is already {row.status.value.lower()}.")
        return self.recommendations.set_status(row, to_status)
