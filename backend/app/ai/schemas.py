"""Typed AI DTOs shared by providers and domain services."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    chunk_id: str = ""
    document_id: str = ""
    score: float = 0.0


class TutorAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    model: str = ""


class TutorStructuredOutput(BaseModel):
    """Validated shape for tutor model output. Citation metadata is NEVER read
    from this object — the application attaches citations from retrieval."""

    model_config = {"extra": "ignore"}

    answer: str = Field(min_length=1, max_length=12000)
    grounded: bool = False
    needs_clarification: bool = False


class ExtractedConcept(BaseModel):
    """One concept as returned by the model. Names are normalized and
    provenance is derived server-side (chunk_refs are advisory only)."""

    model_config = {"extra": "ignore"}

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    chunk_refs: list[int] = Field(default_factory=list)


class ExtractedRelationship(BaseModel):
    """Relationship between two concepts *by name*. Both ends are resolved to
    in-project concepts server-side; anything unresolvable is dropped."""

    model_config = {"extra": "ignore"}

    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    type: str = "RELATED"


class ConceptExtractionResult(BaseModel):
    """Validated envelope for concept-extraction model output."""

    model_config = {"extra": "ignore"}

    concepts: list[ExtractedConcept] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class GeneratedMCQOption(BaseModel):
    """One MCQ option. The model proposes display ids; the application
    validates uniqueness and that the correct id exists."""

    model_config = {"extra": "ignore"}

    id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=2000)


class GeneratedQuestion(BaseModel):
    """One model-proposed quiz question. Concept names are advisory only —
    the application resolves them to in-project concepts and drops unknown
    ones. Provenance (chunks/pages) is NEVER read from this object."""

    model_config = {"extra": "ignore"}

    type: str = Field(min_length=1, max_length=16)
    prompt: str = Field(min_length=1, max_length=4000)
    options: list[GeneratedMCQOption] = Field(default_factory=list)
    correct_option_id: str = Field(default="")
    explanation: str = Field(default="", max_length=4000)
    expected_concepts: list[str] = Field(default_factory=list)
    reference_answer: str = Field(default="", max_length=8000)
    concept_names: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="MEDIUM", max_length=16)


class GeneratedQuestionSet(BaseModel):
    """Validated envelope for question-generation model output."""

    model_config = {"extra": "ignore"}

    questions: list[GeneratedQuestion] = Field(default_factory=list)


class EvaluationUnderstanding(enum.StrEnum):
    FULL = "FULL"
    MOSTLY = "MOSTLY"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class EvaluationAccuracy(enum.StrEnum):
    CORRECT = "CORRECT"
    MOSTLY_CORRECT = "MOSTLY_CORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    INCORRECT = "INCORRECT"


class EvaluationRelevance(enum.StrEnum):
    RELEVANT = "RELEVANT"
    PARTIALLY_RELEVANT = "PARTIALLY_RELEVANT"
    IRRELEVANT = "IRRELEVANT"


class OpenEndedEvaluation(BaseModel):
    """Validated open-ended evaluator output. ``correctness`` is bounded
    0–1; the application clamps and normalizes — a model can never mint an
    unbounded score. ``concepts_understood``/``concepts_missing`` are filtered
    against the question's expected concepts server-side, so hallucinated
    concepts never reach feedback or mastery inputs."""

    model_config = {"extra": "ignore"}

    correctness: float = Field(ge=0.0, le=1.0)
    understanding: EvaluationUnderstanding = EvaluationUnderstanding.PARTIAL
    accuracy: EvaluationAccuracy = EvaluationAccuracy.PARTIALLY_CORRECT
    relevance: EvaluationRelevance = EvaluationRelevance.RELEVANT
    concepts_understood: list[str] = Field(default_factory=list)
    concepts_missing: list[str] = Field(default_factory=list)
    feedback: str = Field(min_length=1, max_length=4000)

    @field_validator("concepts_understood", "concepts_missing", mode="before")
    @classmethod
    def _coerce_str_list(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(v)[:200] for v in value]
        return []
