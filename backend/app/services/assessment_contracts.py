"""Shared assessment result contracts (Prompt 8 output, Prompt 9 input).

``ConceptPerformance`` and ``AssessmentResult`` live here — not in
``assessment_service`` — so ``MasteryService`` can consume them without a
circular import (``AssessmentService`` imports this module too). The
dataclasses are re-exported from ``assessment_service`` for compatibility.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# Score bands (normalized 0-1) shared by assessment aggregation and mastery
# evidence derivation. Partial understanding stays partial — never collapsed
# into fully correct or fully incorrect.
PARTIAL_MIN = 0.3
CORRECT_AT = 0.6


@dataclass
class ConceptPerformance:
    """Per-concept slice of one attempt. ``recent`` holds up to 3 outcomes,
    newest first: ``C`` correct, ``P`` partial, ``I`` incorrect."""

    concept_id: uuid.UUID
    concept_name: str
    questions_seen: int = 0
    correct_count: int = 0
    partial_count: int = 0
    incorrect_count: int = 0
    normalized_score: float = 0.0
    recent: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "concept_id": str(self.concept_id),
            "concept_name": self.concept_name,
            "questions_seen": self.questions_seen,
            "correct_count": self.correct_count,
            "partial_count": self.partial_count,
            "incorrect_count": self.incorrect_count,
            "normalized_score": round(self.normalized_score, 4),
            "recent": list(self.recent),
        }


@dataclass
class AssessmentResult:
    """Completed-attempt summary. Persisted on ``Assessment`` (score 0-100 +
    ``concept_results`` JSON); counts are recomputed from answers so they can
    never drift from stored rows."""

    assessment_id: uuid.UUID
    quiz_attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    total_questions: int
    answered_count: int
    correct_count: int
    partial_count: int
    incorrect_count: int
    score: float
    concept_results: list[ConceptPerformance] = field(default_factory=list)
