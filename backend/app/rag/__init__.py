"""RAG boundary (placeholder). Real pipeline lands in Phase 2+; contracts live here."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    project_id: str
    content: str
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalQuery:
    project_id: str
    question: str
    top_k: int = 8


class Retriever:
    """Project-scoped pgvector retrieval (to be implemented with SQLAlchemy + pgvector)."""

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        raise NotImplementedError("RAG retrieval not implemented yet (foundation phase)")


def build_context(results: list[RetrievalResult], max_chars: int = 12000) -> str:
    """Bounded context builder: never stuff unbounded chunks into the LLM prompt."""
    parts: list[str] = []
    total = 0
    for r in results:
        chunk = f"[chunk {r.chunk_id}] {r.content}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts)
