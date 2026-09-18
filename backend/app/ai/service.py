"""AI service facade: the only entry point domain code should use for AI.

Factories below resolve real vs test providers from centralized Settings, so
routes/services/jobs never branch on environment flags themselves.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai.base import ChatRequest, ChatResponse, EmbedRequest, EmbedResponse
from app.ai.concepts import ConceptExtractor, GroqConceptExtractor
from app.ai.embeddings import EmbeddingService
from app.ai.google_embeddings import GoogleEmbeddingProvider
from app.ai.groq_provider import GroqProvider
from app.core.config import Settings

log = logging.getLogger("app.ai")


class AIService:
    def __init__(
        self,
        chat_provider: GroqProvider | None = None,
        embedding_provider: GoogleEmbeddingProvider | None = None,
    ) -> None:
        # Explicitly injected providers (failure injection in tests, custom
        # wiring in callers) always win over the settings-based test doubles.
        self._explicit_chat_provider = chat_provider is not None
        self._explicit_embedding_provider = embedding_provider is not None
        self.chat_provider = chat_provider or GroqProvider()
        self.embedding_provider = embedding_provider or GoogleEmbeddingProvider()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return await self.chat_provider.chat(request)

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        return await self.embedding_provider.embed(request)

    def embedding_service(self, settings: Settings) -> EmbeddingService:
        """Validated, retried batch embeddings bound to centralized config."""
        from app.ai.fakes import DeterministicEmbeddingProvider

        provider: Any
        if settings.test_fake_ai and not self._explicit_embedding_provider:
            provider = DeterministicEmbeddingProvider(dimensions=settings.embedding_dimensions)
        else:
            provider = self.embedding_provider
        return EmbeddingService(
            provider,
            model=settings.google_embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )

    def concept_extractor(self, settings: Settings) -> ConceptExtractor:
        """Structured concept extraction bound to centralized config."""
        from app.ai.fakes import NaiveKeywordConceptExtractor

        if settings.test_fake_ai:
            return NaiveKeywordConceptExtractor()
        return GroqConceptExtractor(self.chat_provider, model=settings.groq_model_concepts)

    def tutor_chat(self, settings: Settings):
        """Chat provider for Tutor responses. Deterministic fake in tests,
        unless a provider was explicitly injected (e.g. failure injection)."""
        from app.ai.fakes import FakeChatProvider

        if settings.test_fake_ai and not self._explicit_chat_provider:
            return FakeChatProvider()
        return self.chat_provider

    def question_generator(self, settings: Settings):
        """Grounded quiz-question generation bound to centralized config."""
        from app.ai.fakes import FakeChatProvider
        from app.ai.quiz import QuestionGenerator

        if settings.test_fake_ai and not self._explicit_chat_provider:
            return QuestionGenerator(FakeChatProvider(), model=settings.groq_model_quiz)
        return QuestionGenerator(self.chat_provider, model=settings.groq_model_quiz)

    def open_ended_evaluator(self, settings: Settings):
        """Structured open-ended answer evaluation bound to config."""
        from app.ai.fakes import FakeChatProvider
        from app.ai.quiz import OpenEndedEvaluator

        if settings.test_fake_ai and not self._explicit_chat_provider:
            return OpenEndedEvaluator(FakeChatProvider(), model=settings.groq_model_quiz)
        return OpenEndedEvaluator(self.chat_provider, model=settings.groq_model_quiz)


ai_service = AIService()
