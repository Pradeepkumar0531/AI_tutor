"""Material chain + processing-job repositories."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import sqlalchemy as sa

from app.models.enums import JobStatus, MaterialStatus
from app.models.materials import Document, DocumentChunk, DocumentImage, Material
from app.models.ops import ProcessingJob
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class SimilarChunk:
    """One similarity-scored chunk with resolved provenance. Embeddings are
    never included — callers receive scores and text only."""

    chunk: DocumentChunk
    material_id: uuid.UUID
    material_name: str
    document_id: uuid.UUID
    similarity: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Python cosine similarity (SQLite fallback + tests). Zero vectors score 0."""
    if len(a) != len(b):
        raise ValueError(f"cosine_similarity got widths {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


class MaterialRepository(BaseRepository[Material]):
    model = Material

    def create(
        self,
        *,
        project_id: uuid.UUID,
        name: str,
        original_filename: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        storage_key: str | None = None,
        checksum: str | None = None,
    ) -> Material:
        return self.add(
            Material(
                project_id=project_id,
                name=name.strip(),
                original_filename=original_filename,
                mime_type=mime_type,
                file_size=file_size,
                storage_key=storage_key,
                checksum=checksum,
            )
        )

    def get_many_for_project(
        self, material_ids: list[uuid.UUID], project_id: uuid.UUID
    ) -> list[Material]:
        """Batch-resolve materials known to belong to a project (provenance)."""
        if not material_ids:
            return []
        return list(
            self.session.scalars(
                sa.select(Material).where(
                    Material.id.in_(material_ids),
                    Material.project_id == project_id,
                )
            )
        )

    def content_summary(self, project_id: uuid.UUID) -> dict[str, int]:
        """Single-query material counts (non-archived): total, READY, FAILED."""
        from app.models.enums import MaterialStatus

        rows = self.session.execute(
            sa.select(Material.status, sa.func.count(Material.id))
            .where(
                Material.project_id == project_id,
                Material.archived_at.is_(None),
            )
            .group_by(Material.status)
        ).all()
        by_status = {status: total for status, total in rows}
        ready = by_status.get(MaterialStatus.READY, 0)
        failed = by_status.get(MaterialStatus.FAILED, 0)
        return {
            "materials": sum(by_status.values()),
            "ready": ready,
            "failed": failed,
        }

    def get_for_project(
        self,
        material_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> Material | None:
        stmt = sa.select(Material).where(
            Material.id == material_id, Material.project_id == project_id
        )
        if not include_archived:
            stmt = stmt.where(Material.archived_at.is_(None))
        return self.session.scalar(stmt)

    def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        status: MaterialStatus | None = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
    ) -> tuple[list[Material], int]:
        stmt = (
            sa.select(Material)
            .where(Material.project_id == project_id)
            .order_by(Material.created_at.desc())
        )
        if not include_archived:
            stmt = stmt.where(Material.archived_at.is_(None))
        if status is not None:
            stmt = stmt.where(Material.status == status)
        return self.paginate(stmt, page=page, page_size=page_size)


class DocumentRepository(BaseRepository[Document]):
    model = Document

    def project_stats(self, project_id: uuid.UUID) -> tuple[int, int]:
        """(documents, total pages) for non-archived project materials."""
        row = self.session.execute(
            sa.select(
                sa.func.count(Document.id),
                sa.func.coalesce(sa.func.sum(Document.page_count), 0),
            )
            .select_from(Document)
            .join(Material, Material.id == Document.material_id)
            .where(
                Document.project_id == project_id,
                Material.archived_at.is_(None),
            )
        ).one()
        return int(row[0] or 0), int(row[1] or 0)

    def get_for_project(self, document_id: uuid.UUID, project_id: uuid.UUID) -> Document | None:
        return self.session.scalar(
            sa.select(Document).where(Document.id == document_id, Document.project_id == project_id)
        )

    def get_by_material(self, material_id: uuid.UUID, project_id: uuid.UUID) -> Document | None:
        return self.session.scalar(
            sa.select(Document).where(
                Document.material_id == material_id, Document.project_id == project_id
            )
        )


class DocumentImageRepository(BaseRepository[DocumentImage]):
    model = DocumentImage

    def list_for_document(
        self, document_id: uuid.UUID, project_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[DocumentImage], int]:
        """Page-ordered images for one owned document. Bounded like chunks."""
        stmt = (
            sa.select(DocumentImage)
            .where(
                DocumentImage.document_id == document_id,
                DocumentImage.project_id == project_id,
            )
            .order_by(DocumentImage.page_number, DocumentImage.image_index)
        )
        return self.paginate(stmt, page=page, page_size=page_size)

    def get_for_material(
        self, image_id: uuid.UUID, material_id: uuid.UUID, project_id: uuid.UUID
    ) -> DocumentImage | None:
        """Single image verified against its material + project (auth chain)."""
        return self.session.scalar(
            sa.select(DocumentImage).where(
                DocumentImage.id == image_id,
                DocumentImage.material_id == material_id,
                DocumentImage.project_id == project_id,
            )
        )

    def project_total(self, project_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(DocumentImage.id)).where(
                    DocumentImage.project_id == project_id
                )
            )
            or 0
        )

    def count_for_document(self, document_id: uuid.UUID, project_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(DocumentImage.id)).where(
                    DocumentImage.document_id == document_id,
                    DocumentImage.project_id == project_id,
                )
            )
            or 0
        )

    def count_by_page(self, document_id: uuid.UUID, project_id: uuid.UUID) -> dict[int, int]:
        """Page -> image count for knowledge summaries (one grouped query)."""
        rows = self.session.execute(
            sa.select(DocumentImage.page_number, sa.func.count(DocumentImage.id))
            .where(
                DocumentImage.document_id == document_id,
                DocumentImage.project_id == project_id,
            )
            .group_by(DocumentImage.page_number)
        ).all()
        return {page: total for page, total in rows}


class ChunkRepository(BaseRepository[DocumentChunk]):
    model = DocumentChunk

    def project_total(self, project_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(DocumentChunk.id)).where(
                    DocumentChunk.project_id == project_id
                )
            )
            or 0
        )

    def list_for_project(
        self, project_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[DocumentChunk], int]:
        stmt = (
            sa.select(DocumentChunk)
            .where(DocumentChunk.project_id == project_id)
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        return self.paginate(stmt, page=page, page_size=page_size)

    def list_unembedded(
        self, document_id: uuid.UUID, project_id: uuid.UUID, *, limit: int = 200
    ) -> list[DocumentChunk]:
        """Chunks still missing embeddings, in index order. Bounded so one
        run cannot balloon; the job resumes leftovers on retry."""
        return list(
            self.session.scalars(
                sa.select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.project_id == project_id,
                    DocumentChunk.embedding.is_(None),
                )
                .order_by(DocumentChunk.chunk_index)
                .limit(max(1, limit))
            )
        )

    def write_embeddings(self, pairs: list[tuple[uuid.UUID, list[float]]]) -> int:
        """Bulk-assign validated vectors by chunk id. Caller owns the
        transaction; vectors must already pass dimension validation."""
        updated = 0
        connection = self.session.connection()
        for chunk_id, vector in pairs:
            updated += (
                connection.execute(
                    sa.update(DocumentChunk)
                    .where(DocumentChunk.id == chunk_id)
                    .values(embedding=vector)
                ).rowcount
                or 0
            )
        return updated

    def count_embedded(self, project_id: uuid.UUID) -> tuple[int, int]:
        """(total chunks, embedded chunks) for a project, one query."""
        row = self.session.execute(
            sa.select(
                sa.func.count(DocumentChunk.id),
                sa.func.sum(sa.case((DocumentChunk.embedding.is_not(None), 1), else_=0)),
            ).where(DocumentChunk.project_id == project_id)
        ).one()
        return int(row[0] or 0), int(row[1] or 0)

    def count_embedded_for_material(self, material_id: uuid.UUID) -> tuple[int, int]:
        """(total chunks, embedded chunks) for one material's document."""
        row = self.session.execute(
            sa.select(
                sa.func.count(DocumentChunk.id),
                sa.func.sum(sa.case((DocumentChunk.embedding.is_not(None), 1), else_=0)),
            )
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.material_id == material_id)
        ).one()
        return int(row[0] or 0), int(row[1] or 0)

    def search_similar(
        self,
        project_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int = 8,
        material_ids: list[uuid.UUID] | None = None,
    ) -> list[SimilarChunk]:
        """Project-scoped nearest-neighbor search. The project predicate is
        mandatory and lives in the SQL itself — never filter-after-fetch.

        PostgreSQL uses pgvector cosine distance (``<=>``); SQLite (tests/E2E)
        computes the same cosine ordering in Python over project rows.
        """
        if self._dialect() == "postgresql":
            return self._search_pg(project_id, query_vector, limit=limit, material_ids=material_ids)
        return self._search_python(project_id, query_vector, limit=limit, material_ids=material_ids)

    def _dialect(self) -> str:
        bind = self.session.get_bind()
        return bind.dialect.name if bind is not None else "sqlite"

    @staticmethod
    def pg_similarity_stmt(
        project_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        material_ids: list[uuid.UUID] | None = None,
    ) -> sa.Select:
        """PostgreSQL vector query, exposed for dialect validation: mandatory
        project predicate in SQL, cosine distance ordering (``<=>``)."""
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = (
            sa.select(
                DocumentChunk,
                Material.id,
                Material.name,
                Document.id,
                (1 - distance).label("similarity"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(Material, Material.id == Document.material_id)
            .where(
                DocumentChunk.project_id == project_id,
                DocumentChunk.embedding.is_not(None),
                Material.archived_at.is_(None),
            )
            .order_by(distance)
            .limit(limit)
        )
        if material_ids is not None:
            stmt = stmt.where(Document.material_id.in_(material_ids))
        return stmt

    def _search_pg(
        self,
        project_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        material_ids: list[uuid.UUID] | None,
    ) -> list[SimilarChunk]:
        stmt = self.pg_similarity_stmt(
            project_id, query_vector, limit=limit, material_ids=material_ids
        )
        out: list[SimilarChunk] = []
        for chunk, material_id, material_name, document_id, similarity in self.session.execute(
            stmt
        ):
            out.append(
                SimilarChunk(
                    chunk=chunk,
                    material_id=material_id,
                    material_name=material_name,
                    document_id=document_id,
                    similarity=float(similarity),
                )
            )
        return out

    def _search_python(
        self,
        project_id: uuid.UUID,
        query_vector: list[float],
        *,
        limit: int,
        material_ids: list[uuid.UUID] | None,
    ) -> list[SimilarChunk]:
        stmt = (
            sa.select(DocumentChunk, Material.id, Material.name, Document.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(Material, Material.id == Document.material_id)
            .where(
                DocumentChunk.project_id == project_id,
                DocumentChunk.embedding.is_not(None),
                Material.archived_at.is_(None),
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        if material_ids is not None:
            stmt = stmt.where(Document.material_id.in_(material_ids))
        scored: list[SimilarChunk] = []
        for chunk, material_id, material_name, document_id in self.session.execute(stmt):
            embedding = chunk.embedding
            if not isinstance(embedding, list) or not embedding:
                continue
            scored.append(
                SimilarChunk(
                    chunk=chunk,
                    material_id=material_id,
                    material_name=material_name,
                    document_id=document_id,
                    similarity=cosine_similarity(query_vector, [float(x) for x in embedding]),
                )
            )
        scored.sort(key=lambda r: r.similarity, reverse=True)
        return scored[:limit]

    def list_for_document(
        self, document_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[DocumentChunk]:
        """Ordered chunks for context assembly. No limit needed: callers bound usage."""
        return list(
            self.session.scalars(
                sa.select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.project_id == project_id,
                )
                .order_by(DocumentChunk.chunk_index)
            )
        )


class ProcessingJobRepository(BaseRepository[ProcessingJob]):
    model = ProcessingJob

    def enqueue(
        self,
        *,
        job_type: str,
        project_id: uuid.UUID | None = None,
        material_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        payload: dict | None = None,
    ) -> ProcessingJob:
        return self.add(
            ProcessingJob(
                job_type=job_type,
                project_id=project_id,
                material_id=material_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )

    def get_by_idempotency(self, idempotency_key: str) -> ProcessingJob | None:
        return self.session.scalar(
            sa.select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
        )

    def get_pending_for_material(self, material_id: uuid.UUID) -> list[ProcessingJob]:
        return list(
            self.session.scalars(
                sa.select(ProcessingJob).where(
                    ProcessingJob.material_id == material_id,
                    ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]),
                )
            )
        )
