"""Knowledge domain service: status, concept upserts, search delegation.

Route-facing entry points live here (routes stay thin); background embedding
and extraction orchestration lives in ``app.jobs.knowledge_tasks`` following
the document-task pattern. Provenance is stored in the existing
``concepts.metadata`` JSONB — no schema addition was necessary.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.schemas import ConceptExtractionResult
from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import ConceptRelationType, JobStatus
from app.models.knowledge import Concept, ConceptRelationship
from app.models.materials import Document, DocumentChunk, Material
from app.models.ops import ProcessingJob
from app.repositories.intelligence import EventRepository
from app.repositories.knowledge import ConceptRelationshipRepository, ConceptRepository
from app.repositories.materials import ChunkRepository
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.knowledge")

KNOWLEDGE_JOB_TYPE = "knowledge.process"

CONCEPT_SOURCE = "ai-extraction"


@dataclass
class KnowledgeStatus:
    status: Literal["PENDING", "PROCESSING", "READY", "FAILED"]
    chunks_total: int = 0
    chunks_embedded: int = 0
    concepts: int = 0
    materials_ready: int = 0


@dataclass
class ConceptUpsertStats:
    created: int = 0
    updated: int = 0
    relationships_created: int = 0
    relationships_skipped: int = 0


@dataclass
class ProvenanceEntry:
    material_id: uuid.UUID
    material_name: str
    chunk_ids: list[uuid.UUID] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)


def merge_provenance(existing: dict | None, *, entry: ProvenanceEntry, model: str) -> dict:
    """Union provenance by material: replace this material's entry, keep the
    rest. Deterministic key order for stable JSON."""
    materials: dict[str, dict] = {}
    if isinstance(existing, dict):
        for item in existing.get("materials", []):
            if isinstance(item, dict) and item.get("material_id"):
                materials[str(item["material_id"])] = item
    materials[str(entry.material_id)] = {
        "material_id": str(entry.material_id),
        "material_name": entry.material_name,
        "chunk_ids": sorted({str(c) for c in entry.chunk_ids}),
        "pages": sorted(set(entry.pages)),
    }
    return {
        "source": CONCEPT_SOURCE,
        "model": model,
        "materials": [materials[k] for k in sorted(materials)],
    }


def _knowledge_key(material_id: uuid.UUID) -> str:
    from app.jobs.claim import idempotency_key  # lazy: keeps services importable w/o celery

    return idempotency_key(material_id, suffix="knowledge")


class KnowledgeService(BaseService):
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        ai_service=None,  # AIService; untyped to avoid import weight here
    ) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.ai_service = ai_service
        self.projects = ProjectRepository(session)
        self.concepts = ConceptRepository(session)
        self.relationships = ConceptRelationshipRepository(session)
        self.chunks = ChunkRepository(session)
        self.events = EventRepository(session)

    def _ai(self):
        if self.ai_service is None:
            from app.ai.service import ai_service

            return ai_service
        return self.ai_service

    # ------------------------------------------------------------- status

    def get_status(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> KnowledgeStatus:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        total, embedded = self.chunks.count_embedded(project.id)
        concepts = (
            self.session.scalar(
                sa.select(sa.func.count(Concept.id)).where(Concept.project_id == project.id)
            )
            or 0
        )
        materials_ready = (
            self.session.scalar(
                sa.select(sa.func.count(Material.id)).where(
                    Material.project_id == project.id,
                    Material.status == "READY",
                    Material.archived_at.is_(None),
                )
            )
            or 0
        )
        job_states = set(
            self.session.scalars(
                sa.select(ProcessingJob.status).where(
                    ProcessingJob.project_id == project.id,
                    ProcessingJob.job_type == KNOWLEDGE_JOB_TYPE,
                )
            ).all()
        )
        active = bool(job_states & {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING})
        failed = JobStatus.FAILED in job_states
        status: Literal["PENDING", "PROCESSING", "READY", "FAILED"]
        if total == 0:
            status = "PENDING"
        elif active:
            status = "PROCESSING"
        elif embedded == total:
            status = "READY"
        elif failed:
            status = "FAILED"
        elif embedded > 0:
            status = "PROCESSING"  # partial, resumable — no active job needed
        else:
            status = "PENDING"
        return KnowledgeStatus(
            status=status,
            chunks_total=total,
            chunks_embedded=embedded,
            concepts=concepts,
            materials_ready=materials_ready,
        )

    def material_knowledge(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> dict:
        """Per-material knowledge summary for the material detail view."""
        from app.repositories.materials import DocumentRepository, MaterialRepository

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = MaterialRepository(self.session).get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        document = DocumentRepository(self.session).get_by_material(material.id, project.id)
        total, embedded = (0, 0)
        if document is not None:
            total, embedded = self.chunks.count_embedded_for_material(material.id)
        job = self.session.scalar(
            sa.select(ProcessingJob).where(
                ProcessingJob.idempotency_key == _knowledge_key(material.id)
            )
        )
        from app.repositories.materials import DocumentImageRepository

        image_count = 0
        images_by_page: dict[int, int] = {}
        if document is not None:
            image_count = DocumentImageRepository(self.session).count_for_document(
                document.id, project.id
            )
            if image_count:
                images_by_page = DocumentImageRepository(self.session).count_by_page(
                    document.id, project.id
                )
        if total == 0:
            status = "PENDING"
        elif job is not None and job.status in (
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.RETRYING,
        ):
            status = "PROCESSING"
        elif embedded == total:
            status = "READY"
        elif job is not None and job.status == JobStatus.FAILED:
            status = "FAILED"
        elif embedded > 0:
            status = "PROCESSING"
        else:
            status = "PENDING"
        return {
            "status": status,
            "embedded": embedded,
            "total": total,
            "image_count": image_count,
            "images_by_page": images_by_page,
        }

    # ------------------------------------------------------------- concepts

    def list_concepts(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Concept], int]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return self.concepts.list_for_project(project.id, page=page, page_size=page_size)

    def get_concept_detail(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> tuple[Concept, list[dict], int, list[int]]:
        """Concept + resolved material links + supporting-chunk count + pages."""
        from app.repositories.materials import MaterialRepository

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        concept = self.concepts.get_for_project(concept_id, project.id)
        if concept is None:
            raise NotFoundError("Concept not found.")
        provenance = concept.concept_metadata or {}
        material_entries = provenance.get("materials", [])
        material_ids = [
            uuid.UUID(m["material_id"])
            for m in material_entries
            if isinstance(m, dict) and m.get("material_id")
        ]
        materials: list[dict] = []
        chunk_count = 0
        pages: set[int] = set()
        if material_ids:
            for m in MaterialRepository(self.session).get_many_for_project(
                material_ids, project.id
            ):
                materials.append({"id": str(m.id), "name": m.name})
            chunk_count = (
                self.session.scalar(
                    sa.select(sa.func.count(DocumentChunk.id))
                    .select_from(DocumentChunk)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(Document.material_id.in_(material_ids))
                )
                or 0
            )
            for entry in material_entries:
                pages.update(p for p in entry.get("pages", []) if isinstance(p, int))
        materials.sort(key=lambda m: m["name"].lower())
        return concept, materials, chunk_count, sorted(pages)

    @transactional
    def upsert_concepts(
        self,
        *,
        project_id: uuid.UUID,
        extraction: ConceptExtractionResult,
        provenance: ProvenanceEntry,
        model: str,
        max_concepts: int = 20,
    ) -> ConceptUpsertStats:
        """Validate-then-write concept extraction output. No AI calls here —
        the caller already validated the envelope with Pydantic."""
        stats = ConceptUpsertStats()
        by_name: dict[str, Concept] = {}
        for item in extraction.concepts[: max(0, max_concepts)]:
            normalized = Concept.normalize_name(item.name)
            if not normalized:
                continue  # blank names are dropped, never persisted
            concept, created = self.concepts.get_or_create(
                project_id=project_id,
                name=item.name.strip(),
                description=item.description.strip() or None,
            )
            concept.concept_metadata = merge_provenance(
                concept.concept_metadata, entry=provenance, model=model
            )
            if not created and not (concept.description or "").strip() and item.description.strip():
                concept.description = item.description.strip()
                stats.updated += 1
            if created:
                stats.created += 1
            by_name[normalized] = concept
        self.session.flush()
        for rel in extraction.relationships[: max(0, max_concepts) * 2]:
            try:
                rel_type = ConceptRelationType(rel.type.strip().upper())
            except ValueError:
                stats.relationships_skipped += 1
                continue
            source = by_name.get(Concept.normalize_name(rel.source))
            target = by_name.get(Concept.normalize_name(rel.target))
            if source is None or target is None or source.id == target.id:
                stats.relationships_skipped += 1
                continue
            if source.project_id != project_id or target.project_id != project_id:
                stats.relationships_skipped += 1
                continue
            existing = self.session.scalar(
                sa.select(ConceptRelationship).where(
                    ConceptRelationship.project_id == project_id,
                    ConceptRelationship.source_concept_id == source.id,
                    ConceptRelationship.target_concept_id == target.id,
                    ConceptRelationship.relationship_type == rel_type,
                )
            )
            if existing is not None:
                stats.relationships_skipped += 1
                continue
            try:
                with self.session.begin_nested():
                    weight = 1.0
                    self.relationships.link(
                        project_id=project_id,
                        source_id=source.id,
                        target_id=target.id,
                        relationship_type=rel_type,
                        weight=weight,
                    )
                stats.relationships_created += 1
            except Exception:  # noqa: BLE001 - concurrent duplicate: skip, keep going
                log.info("relationship race skipped")
                stats.relationships_skipped += 1
        return stats

    # ------------------------------------------------------------- jobs

    def ensure_knowledge_job(
        self, *, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> ProcessingJob:
        """Get-or-create the knowledge job row. Adds + flushes without
        committing — the caller (job wrapper or transactional service method)
        owns the commit boundary."""
        from app.jobs.claim import get_or_create_job

        return get_or_create_job(
            self.session,
            job_type=KNOWLEDGE_JOB_TYPE,
            project_id=project_id,
            material_id=material_id,
            idempotency_key=_knowledge_key(material_id),
        )

    @transactional
    def reprocess_material_knowledge(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> dict:
        """Reset one material's chunk embeddings to NULL and (re)queue the
        knowledge job. Refuses while a knowledge job is live (409)."""
        from app.repositories.materials import MaterialRepository

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = MaterialRepository(self.session).get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        job = self.session.scalar(
            sa.select(ProcessingJob).where(
                ProcessingJob.idempotency_key == _knowledge_key(material.id)
            )
        )
        if job is not None and job.status in (
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.RETRYING,
        ):
            raise ConflictError("Knowledge processing is already running for this material.")
        reset = (
            self.session.connection()
            .execute(
                sa.update(DocumentChunk)
                .where(
                    DocumentChunk.project_id == project.id,
                    DocumentChunk.document_id.in_(
                        sa.select(Document.id).where(Document.material_id == material.id)
                    ),
                )
                .values(embedding=None)
            )
            .rowcount
            or 0
        )
        job = self.ensure_knowledge_job(project_id=project.id, material_id=material.id)
        job.status = JobStatus.QUEUED
        job.error = None
        job.attempt_count = 0
        job.started_at = None
        job.completed_at = None
        return {"material_id": str(material.id), "job_status": job.status.value, "reset": reset}

    # ------------------------------------------------------------- search

    async def search(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        material_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        """Route-facing search: delegates retrieval, returns JSON-safe result."""
        from app.rag.retrieval import RetrievalService

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        settings = self.settings
        top_k = min(max(top_k if top_k is not None else settings.rag_top_k, 1), 50)
        threshold = min(
            max(threshold if threshold is not None else settings.rag_similarity_threshold, 0.0), 1.0
        )
        embedding_service = self._ai().embedding_service(settings)
        service = RetrievalService(self.session, embedding_service, settings)
        result = await service.search(
            user_id=user_id,
            project_id=project.id,
            query=query,
            top_k=top_k,
            threshold=threshold,
            material_ids=material_ids,
            max_chunks=settings.rag_max_context_chunks,
            max_chars=settings.rag_max_context_chars,
        )
        return {
            "query": result.query,
            "results": [
                {
                    "chunk_id": str(r.chunk_id),
                    "document_id": str(r.document_id),
                    "material_id": str(r.material_id),
                    "material_name": r.material_name,
                    "text": r.text,
                    "page_start": r.page_start,
                    "page_end": r.page_end,
                    "similarity": round(r.similarity, 4),
                }
                for r in result.results
            ],
            "citations": [
                {
                    "chunk_id": str(c.chunk_id),
                    "document_id": str(c.document_id),
                    "material_id": str(c.material_id),
                    "material_name": c.material_name,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                }
                for c in result.citations
            ],
            "context": result.context.text,
            "insufficient_evidence": result.insufficient_evidence,
        }
