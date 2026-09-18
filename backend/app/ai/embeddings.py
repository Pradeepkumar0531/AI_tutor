"""Batch embedding orchestration with validation, retries, and observability.

The provider performs raw calls; this service owns batching (order-preserving),
transient retry with backoff, timeouts, and strict response validation. Only
validated vectors ever leave here — malformed output fails the job, never
PostgreSQL.
"""

from __future__ import annotations

import asyncio
import logging
import math

from app.ai.base import EmbedRequest, EmbedResponse
from app.ai.errors import (
    AITransientError,
    EmbeddingDimensionMismatch,
    EmbeddingProviderUnavailable,
    EmbeddingResponseInvalid,
)
from app.ai.observability import log_ai_call, timed_ai_call
from app.core.exceptions import AppError

log = logging.getLogger("app.ai.embeddings")


class EmbeddingService:
    def __init__(
        self,
        provider,
        *,
        model: str,
        dimensions: int,
        batch_size: int = 32,
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.provider = provider
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "name", type(self.provider).__name__)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed preserving input order. Empty input returns [] without a call."""
        if not texts:
            return []
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise ValueError(f"cannot embed blank text at index {i}")
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            out.extend(await self._embed_batch_with_retry(batch))
        return out

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    # Aliases matching the canonical provider vocabulary.
    async def embed_text(self, text: str) -> list[float]:
        return await self.embed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self.embed_texts(texts)

    async def _embed_batch_with_retry(self, batch: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with timed_ai_call() as timer:
                    response = await asyncio.wait_for(
                        self.provider.embed(EmbedRequest(texts=batch, model=self.model)),
                        timeout=self.timeout_seconds,
                    )
                vectors = self._validate(batch, response)
                log_ai_call(
                    provider=self.provider_name,
                    model=self.model,
                    operation="embed",
                    latency_ms=timer.latency_ms,
                    status="ok",
                    batch_size=len(batch),
                )
                return vectors
            except (EmbeddingProviderUnavailable, AITransientError, TimeoutError) as e:
                last_error = e
                last_error = e
                log_ai_call(
                    provider=self.provider_name,
                    model=self.model,
                    operation="embed",
                    latency_ms=0,
                    status="retry" if attempt < self.max_retries else "failed",
                    batch_size=len(batch),
                    error_type=type(e).__name__,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(min(30.0, 2.0**attempt))
            except AppError:
                # Already-classified taxonomy errors pass through unwrapped so
                # permanent failures are never misreported as transient or vice versa.
                raise
            except Exception as e:  # noqa: BLE001 - unknown SDK failure: do not retry blindly
                log_ai_call(
                    provider=self.provider_name,
                    model=self.model,
                    operation="embed",
                    latency_ms=0,
                    status="failed",
                    batch_size=len(batch),
                    error_type=type(e).__name__,
                )
                raise EmbeddingResponseInvalid(f"Embedding call failed: {type(e).__name__}") from e
        assert last_error is not None
        if isinstance(last_error, EmbeddingProviderUnavailable):
            raise last_error
        raise EmbeddingProviderUnavailable(f"Embedding timed out: {last_error}") from last_error

    def _validate(self, batch: list[str], response: EmbedResponse) -> list[list[float]]:
        vectors = response.embeddings
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise EmbeddingResponseInvalid(
                f"Expected {len(batch)} vectors, got "
                f"{len(vectors) if isinstance(vectors, list) else type(vectors).__name__}."
            )
        for i, vec in enumerate(vectors):
            if not isinstance(vec, (list, tuple)) or len(vec) != self.dimensions:
                raise EmbeddingDimensionMismatch(
                    f"Vector {i} has width "
                    f"{len(vec) if isinstance(vec, (list, tuple)) else '?'}; "
                    f"expected {self.dimensions}. Refusing to persist."
                )
            if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vec):
                raise EmbeddingResponseInvalid(f"Vector {i} contains non-finite values.")
        return [list(map(float, v)) for v in vectors]
