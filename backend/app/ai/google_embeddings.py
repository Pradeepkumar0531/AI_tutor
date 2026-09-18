"""Google embedding provider (lazy SDK import so API boots without keys).

Performs raw calls only: batching, retries, timeouts, and response validation
live in ``EmbeddingService``. SDK failures are classified here into the shared
error taxonomy (transient vs permanent) without leaking keys or payloads.
"""

from __future__ import annotations

from app.ai.base import EmbedRequest, EmbedResponse
from app.ai.errors import EmbeddingConfigurationError, EmbeddingProviderUnavailable
from app.core.config import get_settings


def _classify_sdk_error(error: Exception) -> Exception:
    """Map google.api_core failures to transient/permanent buckets by type name
    (avoids importing SDK internals at module scope)."""
    name = type(error).__name__
    transient = {
        "DeadlineExceeded",
        "ServiceUnavailable",
        "Internal",
        "Aborted",
        "Cancelled",
        "ResourceExhausted",
        "Unknown",
        "ServerError",
        "BadGateway",
    }
    permanent = {
        "Unauthenticated",
        "PermissionDenied",
        "InvalidArgument",
        "NotFound",
        "FailedPrecondition",
    }
    if name in transient:
        return EmbeddingProviderUnavailable(f"Google embeddings transient failure: {name}.")
    if name in permanent:
        return EmbeddingConfigurationError(f"Google embeddings rejected the request: {name}.")
    return EmbeddingProviderUnavailable(f"Google embeddings call failed: {name}.")


class GoogleEmbeddingProvider:
    name = "google-embeddings"

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        settings = get_settings()
        if not settings.google_api_key:
            raise EmbeddingConfigurationError("GOOGLE_API_KEY is not configured.")
        import google.generativeai as genai  # lazy import

        genai.configure(api_key=settings.google_api_key)
        timeout = getattr(settings, "embedding_timeout_seconds", 60)
        # Matryoshka truncation: current Gemini embedding models default to
        # 3072-d; the schema is fixed VECTOR(768), so request 768 explicitly.
        dimensions = getattr(settings, "google_embedding_dimensions", 0) or 0
        out: list[list[float]] = []
        for text in request.texts:
            try:
                kwargs: dict = {
                    "model": request.model,
                    "content": text,
                    "request_options": {"timeout": timeout},
                }
                if dimensions > 0:
                    kwargs["output_dimensionality"] = dimensions
                result = genai.embed_content(**kwargs)
                out.append(list(result["embedding"]))
            except (EmbeddingConfigurationError, EmbeddingProviderUnavailable):
                raise
            except Exception as e:  # noqa: BLE001 - classified below, never raw
                classified = _classify_sdk_error(e)
                classified.__cause__ = e
                raise classified from e
        return EmbedResponse(embeddings=out, model=request.model)
