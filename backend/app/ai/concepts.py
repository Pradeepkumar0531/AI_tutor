"""Concept extraction behind a protocol. Production uses Groq structured JSON;
tests and the E2E worker (via an explicit env flag) use the keyword extractor
in ``app.ai.fakes``. Callers depend on ``ConceptExtractor``, never on Groq."""

from __future__ import annotations

import logging
from typing import Protocol

from app.ai.prompts import build_concept_extraction_prompt
from app.ai.schemas import ConceptExtractionResult

log = logging.getLogger("app.ai.concepts")


class ConceptExtractor(Protocol):
    async def extract(self, source_text: str, *, max_concepts: int) -> ConceptExtractionResult: ...


class GroqConceptExtractor:
    """Structured-JSON concept extraction via the shared Groq provider."""

    def __init__(self, chat_provider, *, model: str) -> None:
        self.chat_provider = chat_provider
        self.model = model
        self.name = "groq-concepts"

    async def extract(self, source_text: str, *, max_concepts: int) -> ConceptExtractionResult:
        from app.ai.errors import ConceptExtractionFailed

        if not source_text or not source_text.strip():
            raise ConceptExtractionFailed("Cannot extract concepts from empty text.")
        system, user = build_concept_extraction_prompt(source_text, max_concepts=max_concepts)
        raw = await self.chat_provider.chat_json(system=system, user=user, model=self.model)
        try:
            return ConceptExtractionResult.model_validate(raw)
        except Exception as e:
            log.warning("concept extraction output failed validation err=%s", e)
            raise ConceptExtractionFailed("Concept extraction returned malformed output.") from e
