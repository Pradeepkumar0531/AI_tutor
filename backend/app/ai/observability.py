"""Structured AI request logging. One log line per provider call with exactly the
fields operations needs — never keys, prompts, documents, or raw payloads."""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("app.ai")


def log_ai_call(
    *,
    provider: str,
    model: str,
    operation: str,
    latency_ms: int,
    status: str,
    batch_size: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error_type: str | None = None,
    project_id: Any | None = None,
    material_id: Any | None = None,
    conversation_id: Any | None = None,
    retrieved_chunk_count: int | None = None,
    quiz_id: Any | None = None,
    attempt_id: Any | None = None,
    question_type: str | None = None,
    question_count: int | None = None,
    concept_count: int | None = None,
) -> None:
    """Emit a single structured line. Token counts are recorded only when the
    provider actually reports them — never fabricated. Learner answers and
    reference answers are never logged."""
    log.info(
        "ai_call provider=%s model=%s operation=%s latency_ms=%s status=%s "
        "batch_size=%s input_tokens=%s output_tokens=%s error_type=%s "
        "project_id=%s material_id=%s conversation_id=%s retrieved_chunks=%s "
        "quiz_id=%s attempt_id=%s question_type=%s question_count=%s concept_count=%s",
        provider,
        model,
        operation,
        latency_ms,
        status,
        batch_size if batch_size is not None else "-",
        input_tokens if input_tokens is not None else "-",
        output_tokens if output_tokens is not None else "-",
        error_type or "-",
        project_id or "-",
        material_id or "-",
        conversation_id or "-",
        retrieved_chunk_count if retrieved_chunk_count is not None else "-",
        quiz_id or "-",
        attempt_id or "-",
        question_type or "-",
        question_count if question_count is not None else "-",
        concept_count if concept_count is not None else "-",
    )


class timed_ai_call:
    """Context manager measuring latency for log_ai_call."""

    def __init__(self) -> None:
        self.started = time.perf_counter()

    def __enter__(self) -> timed_ai_call:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    @property
    def latency_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)
