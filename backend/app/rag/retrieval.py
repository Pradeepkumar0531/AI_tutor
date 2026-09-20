"""Project-scoped vector retrieval + grounded context building.


Non-negotiable rules enforced here:
1. Every retrieval filters ``document_chunks.project_id`` in the database query
   itself — never fetch-globally-then-filter.
2. Retrieved text is untrusted data. Context is wrapped in explicit source
   delimiters; citations are constructed by the application from chunk
   provenance, never by the model.
3. Embeddings never leave this layer (no API field carries a vector).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.prompts import SOURCE_BEGIN, SOURCE_END
from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.materials import DocumentChunk
from app.repositories.materials import ChunkRepository, SimilarChunk
from app.repositories.projects import ProjectRepository

log = logging.getLogger("app.rag")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    document_id: uuid.UUID
    text: str
    page_start: int | None
    page_end: int | None
    similarity: float


@dataclass(frozen=True)
class Citation:
    """Application-owned citation. Page numbers come from chunk provenance —
    a model can never invent them because it never constructs this object."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    page_start: int | None
    page_end: int | None

    def label(self) -> str:
        if self.page_start is None and self.page_end is None:
            return f"{self.material_name} — page unknown"
        if self.page_end is None or self.page_end == self.page_start:
            return f"{self.material_name} — Page {self.page_start}"
        return f"{self.material_name} — Pages {self.page_start}–{self.page_end}"


@dataclass
class RAGContext:
    text: str
    citations: list[Citation] = field(default_factory=list)
    chunk_count: int = 0
    truncated: bool = False
    insufficient_evidence: bool = False


@dataclass
class SearchResult:
    query: str
    results: list[RetrievedChunk]
    citations: list[Citation]
    context: RAGContext
    insufficient_evidence: bool
    best_similarity: float | None = None


def _normalize_for_dedup(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def format_image_references(images: list) -> str:
    """Render extracted document images as evidence metadata blocks.

    Extension point for future multimodal retrieval (NOT wired into the
    default text context): the blocks describe where images exist — document,
    page, index, type, dimensions — and MUST NEVER claim anything about an
    image's semantic contents (no vision model reads them yet). Each entry
    accepts either a ``DocumentImage`` row or a mapping with the same keys.
    """

    def field(item: object, name: str, default: object = None) -> object:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    parts = []
    for index, image in enumerate(images, start=1):
        parts.append(
            "[IMAGE]\n"
            f"Reference: {index}\n"
            f"Document: {field(image, 'document_id')}\n"
            f"Page: {field(image, 'page_number')}\n"
            f"Image: {field(image, 'image_index')}\n"
            f"Type: {field(image, 'mime_type')}\n"
            f"Dimensions: {field(image, 'width')}x{field(image, 'height')}\n"
            "[/IMAGE]"
        )
    return "\n\n".join(parts)


def format_chunks_for_prompt(chunks: list) -> str:
    """Render retrieved chunks as labeled source blocks WITHOUT trust-boundary
    delimiters — prompt builders own the single SOURCE_BEGIN/END wrapper."""
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        page = format_page_range(chunk.page_start, chunk.page_end)
        parts.append(
            f"[Source {index}] {chunk.material_name} — {page} "
            f"(similarity {chunk.similarity:.2f})\n{chunk.text.strip()}"
        )
    return "\n\n".join(parts)


def format_page_range(page_start: int | None, page_end: int | None) -> str:
    if page_start is None and page_end is None:
        return "Page ?"
    if page_end is None or page_end == page_start:
        return f"Page {page_start}"
    return f"Pages {page_start}–{page_end}"


def build_rag_context(
    results: list[RetrievedChunk], *, max_chunks: int, max_chars: int
) -> RAGContext:
    """Assemble bounded, deduplicated, provenance-preserving context.

    Deterministic: input order (similarity desc) decides keep order; exact
    text duplicates keep the first (strongest) occurrence with its own
    provenance. Nothing is merged across chunks.
    """
    if max_chunks < 1 or max_chars < 1:
        raise ValueError("max_chunks and max_chars must be positive")
    kept: list[RetrievedChunk] = []
    seen: set[str] = set()
    for result in results:
        if len(kept) >= max_chunks:
            break
        key = _normalize_for_dedup(result.text)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(result)
    blocks: list[str] = []
    citations: list[Citation] = []
    total = 0
    truncated = len(kept) < len([r for r in results if _normalize_for_dedup(r.text)])
    for n, result in enumerate(kept, start=1):
        block = (
            f"[Source {n}] {result.material_name} — "
            f"{format_page_range(result.page_start, result.page_end)} "
            f"(similarity {result.similarity:.2f})\n{result.text}"
        )
        if total + len(block) > max_chars:
            if not blocks:
                # A single oversized chunk: truncate it rather than exceed budget.
                blocks.append(block[:max_chars])
                citations.append(
                    Citation(
                        chunk_id=result.chunk_id,
                        document_id=result.document_id,
                        material_id=result.material_id,
                        material_name=result.material_name,
                        page_start=result.page_start,
                        page_end=result.page_end,
                    )
                )
            truncated = True
            break
        blocks.append(block)
        total += len(block)
        citations.append(
            Citation(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                material_id=result.material_id,
                material_name=result.material_name,
                page_start=result.page_start,
                page_end=result.page_end,
            )
        )
    if not blocks:
        return RAGContext(
            text="", citations=[], chunk_count=0, truncated=False, insufficient_evidence=True
        )
    text = f"{SOURCE_BEGIN}\n\n" + "\n\n".join(blocks) + f"\n\n{SOURCE_END}"
    return RAGContext(
        text=text,
        citations=citations,
        chunk_count=len(blocks),
        truncated=truncated,
        insufficient_evidence=False,
    )


class RetrievalService:
    """Project-scoped pgvector retrieval. Constructed per call with the
    request session and a configured embedding service."""

    def __init__(self, session: Session, embedding_service, settings: Settings) -> None:
        self.session = session
        self.embedding_service = embedding_service
        self.settings = settings
        self.chunks = ChunkRepository(session)
        self.projects = ProjectRepository(session)

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        material_ids: list[uuid.UUID] | None = None,
        max_chunks: int | None = None,
        max_chars: int | None = None,
    ) -> SearchResult:
        cleaned = (query or "").strip()
        if not cleaned:
            raise BadRequestError("Search query must not be empty.")
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            # Non-disclosing: cross-tenant and missing projects look identical.
            raise NotFoundError("Project not found.")
        return await self._execute(
            project_id=project.id,
            query=cleaned,
            top_k=top_k,
            threshold=threshold,
            material_ids=material_ids,
            max_chunks=max_chunks,
            max_chars=max_chars,
        )

    async def diagnose_for_admin(
        self,
        *,
        project_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
    ) -> SearchResult:
        """Ownership-blind retrieval for the admin RAG diagnostic endpoint.
        The route is already gated by server-side ``require_admin``; unlike
        ``search`` this resolves the project directly so admins can inspect
        any tenant's retrieval health. Never returns vectors."""
        from app.models.learning import Project

        cleaned = (query or "").strip()
        if not cleaned:
            raise BadRequestError("Search query must not be empty.")
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return await self._execute(project_id=project.id, query=cleaned, top_k=top_k)

    async def _execute(
        self,
        *,
        project_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        material_ids: list[uuid.UUID] | None = None,
        max_chunks: int | None = None,
        max_chars: int | None = None,
    ) -> SearchResult:
        top_k = min(max(top_k if top_k is not None else self.settings.rag_top_k, 1), 50)
        threshold = min(
            max(
                threshold if threshold is not None else self.settings.rag_similarity_threshold,
                0.0,
            ),
            1.0,
        )
        max_chunks = min(
            max(max_chunks if max_chunks is not None else self.settings.rag_max_context_chunks, 1),
            50,
        )
        max_chars = min(
            max(max_chars if max_chars is not None else self.settings.rag_max_context_chars, 256),
            200_000,
        )

        started = time.perf_counter()
        query_vector = await self.embedding_service.embed_query(query)
        scored = self.chunks.search_similar(
            project_id, query_vector, limit=top_k, material_ids=material_ids
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        results = [self._to_retrieved(s) for s in scored if s.similarity >= threshold]
        best = results[0].similarity if results else None
        insufficient = not results
        context = build_rag_context(results, max_chunks=max_chunks, max_chars=max_chars)
        context.insufficient_evidence = insufficient
        log.info(
            "rag search project_id=%s top_k=%s threshold=%s returned=%s best=%s "
            "insufficient=%s latency_ms=%s",
            project_id,
            top_k,
            round(threshold, 3),
            len(results),
            round(best, 3) if best is not None else "-",
            insufficient,
            latency_ms,
        )
        return SearchResult(
            query=query,
            results=results,
            citations=context.citations,
            context=context,
            insufficient_evidence=insufficient,
            best_similarity=best,
        )

    @staticmethod
    def _to_retrieved(similar: SimilarChunk) -> RetrievedChunk:
        chunk: DocumentChunk = similar.chunk
        return RetrievedChunk(
            chunk_id=chunk.id,
            material_id=similar.material_id,
            material_name=similar.material_name,
            document_id=similar.document_id,
            text=chunk.content,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            similarity=similar.similarity,
        )
