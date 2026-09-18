"""Groq LLM provider (lazy SDK import so API boots without keys)."""

from __future__ import annotations

from typing import Any

from app.ai.base import ChatRequest, ChatResponse
from app.core.config import get_settings


class GroqProvider:
    name = "groq"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        from groq import AsyncGroq  # lazy: keeps startup light

        client = AsyncGroq(api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds)
        messages: list[Any] = [{"role": m.role, "content": m.content} for m in request.messages]
        completion = await client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        content = completion.choices[0].message.content or ""
        return ChatResponse(content=content, model=request.model)

    async def chat_json(
        self, *, system: str, user: str, model: str, max_tokens: int | None = None
    ) -> dict:
        """Chat with JSON-object response mode for structured extraction. Returns
        the parsed object. Timeout/connection/rate-limit/5xx failures raise
        AITransientError (retryable); everything else becomes
        ConceptExtractionFailed (permanent). Never raw SDK errors, never keys."""
        from app.ai.errors import AITransientError, ConceptExtractionFailed

        settings = get_settings()
        if not settings.groq_api_key:
            raise ConceptExtractionFailed("AI service is not configured.")
        from groq import AsyncGroq  # lazy: keeps startup light

        client = AsyncGroq(api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds)
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=max_tokens or 4000,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content or ""
        except (ConceptExtractionFailed, AITransientError):
            raise
        except Exception as e:  # noqa: BLE001 - classified below, never raw
            raise self._classify_chat_error(e) from e
        import json as _json

        try:
            parsed = _json.loads(content)
        except Exception as e:
            raise ConceptExtractionFailed("Concept extraction returned malformed output.") from e
        if not isinstance(parsed, dict):
            raise ConceptExtractionFailed("Concept extraction returned malformed output.")
        return parsed

    @staticmethod
    def _classify_chat_error(error: Exception) -> Exception:
        """Timeouts, connection failures, rate limits, and 5xx are transient;
        auth errors and everything else are permanent extraction failures."""
        from app.ai.errors import AITransientError, ConceptExtractionFailed

        name = type(error).__name__
        status = getattr(error, "status_code", None)
        transient_names = {
            "APITimeoutError",
            "TimeoutError",
            "APIConnectionError",
            "RateLimitError",
            "InternalServerError",
            "ServiceUnavailableError",
            "BadGatewayError",
            "GatewayTimeoutError",
        }
        if name in transient_names or (isinstance(status, int) and 500 <= status < 600):
            return AITransientError(f"Concept model temporarily unavailable: {name}.")
        return ConceptExtractionFailed(f"Concept extraction call failed: {name}.")
