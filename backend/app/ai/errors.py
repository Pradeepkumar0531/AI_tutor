"""AI/knowledge error taxonomy. All errors flow through the shared envelope;
provider internals (stack traces, keys, raw payloads) never reach HTTP."""

from __future__ import annotations

from app.core.exceptions import AppError


class KnowledgeProcessingFailed(AppError):
    code = "KNOWLEDGE_PROCESSING_FAILED"
    message = "Knowledge processing failed."
    status_code = 500


class EmbeddingConfigurationError(AppError):
    """Permanent: missing/bad key, unsupported model, dimension mismatch in config."""

    code = "EMBEDDING_CONFIGURATION_ERROR"
    message = "Embedding service is not configured correctly."
    status_code = 500


class EmbeddingProviderUnavailable(AppError):
    """Transient: timeouts, rate limits, 5xx, network errors. Safe to retry."""

    code = "EMBEDDING_PROVIDER_UNAVAILABLE"
    message = "Embedding service is temporarily unavailable."
    status_code = 503


class AITransientError(AppError):
    """Transient failure from any AI provider (chat/completion path): timeouts,
    connection errors, rate limits, 5xx. Safe to retry with backoff."""

    code = "AI_TRANSIENT_ERROR"
    message = "AI service is temporarily unavailable."
    status_code = 503


class EmbeddingDimensionMismatch(AppError):
    """Permanent: provider returned vectors of the wrong width. Never persisted."""

    code = "EMBEDDING_DIMENSION_MISMATCH"
    message = "Embedding service returned vectors of unexpected dimensions."
    status_code = 500


class EmbeddingResponseInvalid(AppError):
    """Permanent: count mismatch, non-finite values, malformed payload."""

    code = "EMBEDDING_RESPONSE_INVALID"
    message = "Embedding service returned an invalid response."
    status_code = 500


class ConceptExtractionFailed(AppError):
    """Permanent: malformed model output after validation, or unusable config."""

    code = "CONCEPT_EXTRACTION_FAILED"
    message = "Concept extraction failed."
    status_code = 500


class TutorGenerationFailed(AppError):
    """Permanent: malformed tutor output after validation, or unusable config."""

    code = "TUTOR_GENERATION_FAILED"
    message = "Tutor response generation failed."
    status_code = 500


class QuizGenerationFailed(AppError):
    """Permanent: malformed quiz output after bounded validation/retries, or
    unusable quiz config."""

    code = "QUIZ_GENERATION_FAILED"
    message = "Quiz generation failed."
    status_code = 500


class QuizEvaluationFailed(AppError):
    """Permanent: open-ended evaluator returned invalid output after bounded
    retries. The learner's answer stays persisted; only evaluation failed."""

    code = "QUIZ_EVALUATION_FAILED"
    message = "Answer evaluation failed."
    status_code = 500


class QuizInsufficientEvidence(AppError):
    """No concept yielded enough project evidence to build the requested quiz."""

    code = "QUIZ_INSUFFICIENT_EVIDENCE"
    message = "Not enough project evidence to build this quiz."
    status_code = 422


class InsufficientEvidence(AppError):
    """Raised only by explicit require-evidence helpers (search itself returns a
    flag instead of raising, so future Tutor callers can choose)."""

    code = "INSUFFICIENT_EVIDENCE"
    message = "Not enough evidence in this project's materials."
    status_code = 200
